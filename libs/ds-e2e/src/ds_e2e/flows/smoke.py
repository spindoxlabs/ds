from __future__ import annotations

import json
import logging
import time
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.http import HttpError
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
FINAL_TRANSFER_STATES = {"STARTED"}
REQUIRED_PROVENANCE_EVENTS = {
    "CataloguePublished",
    "CatalogViewed",
    "AccessRequested",
    "NegotiationStarted",
    "NegotiationFinalized",
    "ContractAgreementSigned",
    "TransferStarted",
    "QueryExecuted",
    "AccessRevoked",
}


class SmokeFlow(BaseFlow):
    name = "smoke"
    description = "Full DSP consumer-pull flow: catalog, negotiate, transfer, query, revoke"

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        # 1. Health
        if not self._check_health(result):
            return result

        # 2. Service token
        try:
            self.http.acquire_service_token()
            result.pass_step("service token", "acquired Keycloak service token")
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        svc_headers = self.http.bearer_headers()

        # 3. Provider sync
        try:
            sync = self.http.post(f"{s.connector_url}/provider/sync", {}, headers=svc_headers) or {}
            result.pass_step("provider sync", "governance published to provider EDC", synced=len(sync.get("synced") or []))
        except Exception as exc:
            result.fail_step("provider sync", str(exc))
            return result

        # 4. Load credentials
        consumer_vc, subject_vc = self._fetch_credentials(result, svc_headers)
        if consumer_vc is None:
            return result

        consumer_headers = {
            "X-Subject-Id": s.consumer_subject_id,
            "X-User-VC": consumer_vc,
        }
        subject_headers = {
            "X-Subject-Id": s.data_subject_id,
            "X-User-VC": subject_vc,
        }

        # 5. Catalog discovery
        catalog_body = {
            "counter_party_address": s.counter_party_address,
            "counter_party_id": s.provider_did,
        }
        try:
            catalog = self.http.post(
                f"{s.consumer_connector_url}/consumer/catalog",
                catalog_body,
                headers=consumer_headers,
            ) or {}
            dataset = self._select_dataset(catalog)
            if not dataset:
                result.fail_step("catalog discovery", "catalog has no datasets")
                return result
            asset_id = str(dataset.get("@id") or dataset.get("id") or s.asset_id)
            result.pass_step("catalog discovery", "consumer discovered provider catalog", asset_id=asset_id)
        except Exception as exc:
            result.fail_step("catalog discovery", str(exc))
            return result

        # 6. Consent grant
        try:
            share_body = {
                "dataset_id": asset_id,
                "consumer_id": s.consumer_did,
                "enabled": True,
                "purpose": ["ds:purpose:EnergyBalancing"],
            }
            share = self.http.post(
                f"{s.connector_url}/consent/my/shares", share_body, headers=subject_headers
            ) or {}
            result.pass_step("consent grant", "data subject granted standing data sharing", consent_id=share.get("id"))
        except Exception as exc:
            result.fail_step("consent grant", str(exc))
            return result

        # 7. Negotiate
        policy = self._policy(dataset)
        offer_id = str(policy.get("@id") or f"{asset_id}#offer")
        negotiate_body = {
            "counter_party_address": s.counter_party_address,
            "offer_id": offer_id,
            "asset_id": asset_id,
            "assigner": s.provider_did,
            "odrl_policy": policy or None,
        }
        try:
            negotiated = self.http.post(
                f"{s.consumer_connector_url}/consumer/negotiate",
                negotiate_body,
                headers=consumer_headers,
            ) or {}
            negotiation_id = negotiated["negotiation_id"]
            result.pass_step("request access", "negotiation started", negotiation_id=negotiation_id)
        except Exception as exc:
            result.fail_step("request access", str(exc))
            return result

        # 8. Poll negotiation
        encoded_neg_id = urllib.parse.quote(negotiation_id, safe="")
        negotiation = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/negotiations/{encoded_neg_id}",
            lambda p: p.get("state") in FINAL_NEGOTIATION_STATES and bool(p.get("contractAgreementId")),
            headers=consumer_headers,
        )
        agreement_id = negotiation.get("contractAgreementId")
        if not agreement_id:
            result.fail_step(
                "negotiation DSP",
                "negotiation did not finalize",
                state=negotiation.get("state"),
            )
            return result
        result.pass_step("negotiation DSP", "contract negotiation finalized", agreement_id=agreement_id)

        # 9. Transfer
        transfer_body = {
            "contract_agreement_id": agreement_id,
            "counter_party_address": s.counter_party_address,
            "asset_id": asset_id,
            "connector_id": s.provider_did,
        }
        try:
            transfer = self.http.post(
                f"{s.consumer_connector_url}/consumer/transfer",
                transfer_body,
                headers=consumer_headers,
            ) or {}
            transfer_id = transfer["transfer_id"]
        except Exception as exc:
            result.fail_step("transfer EDR", str(exc))
            return result

        # 10. Poll transfer
        encoded_transfer_id = urllib.parse.quote(transfer_id, safe="")
        transfer_state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/transfers/{encoded_transfer_id}",
            lambda p: p.get("state") in FINAL_TRANSFER_STATES,
            headers=consumer_headers,
        )
        if transfer_state.get("state") not in FINAL_TRANSFER_STATES:
            result.fail_step("transfer EDR", "transfer did not reach STARTED", transfer_id=transfer_id)
            return result
        result.pass_step("transfer EDR", "EDR-gated transfer started", transfer_id=transfer_id)

        # 11. Query dataset-api
        query_params = urllib.parse.urlencode({
            "dataset_name": asset_id,
            "consumer_id": s.consumer_did,
            "subject_id": s.data_subject_id,
            "agreement_id": agreement_id,
            "transfer_id": transfer_id,
        })
        status, query_payload = self.http.get_raw(f"{s.dataset_api_url}/query?{query_params}")
        if status != 200 or not isinstance(query_payload, dict) or query_payload.get("count", 0) < 1:
            result.fail_step("query consentita", "expected at least one authorized row", status_code=status)
            return result
        result.pass_step("query consentita", "consent and active transfer allow data query", rows=query_payload.get("count"))

        # 12. Revoke
        requests_payload = self.http.get(
            f"{s.consumer_connector_url}/consumer/requests", headers=consumer_headers
        ) or []
        request_id = None
        for item in requests_payload:
            if item.get("negotiation_id") == negotiation_id or item.get("transfer_id") == transfer_id:
                request_id = item.get("id")
                break
        if not request_id:
            result.fail_step("revoke access", "could not find persisted access request")
            return result

        revoke = self.http.post(
            f"{s.consumer_connector_url}/consumer/requests/{urllib.parse.quote(str(request_id), safe='')}/revoke",
            {"reason": "e2e-verification"},
            headers=consumer_headers,
        ) or {}
        if revoke.get("status") != "revoked":
            result.fail_step("revoke access", "revoke did not return revoked", response=revoke)
            return result
        result.pass_step("revoke access", "consumer access and agreement revoked", request_id=request_id)

        # 13. Query blocked after revoke (poll — DSP termination propagates async)
        blocked_deadline = time.time() + s.poll_timeout
        blocked_status = 0
        while time.time() < blocked_deadline:
            blocked_status, _ = self.http.get_raw(f"{s.dataset_api_url}/query?{query_params}")
            if blocked_status == 403:
                break
            time.sleep(s.poll_interval)
        if blocked_status != 403:
            result.fail_step("query blocked after revoke", "expected 403", status_code=blocked_status)
            return result
        result.pass_step("query blocked after revoke", "stale transfer cannot query after revoke")

        # 14. Provenance (merge events from provider + consumer instances)
        event_types: set[str] = set()
        for prov_url in (s.provenance_url, s.consumer_provenance_url):
            events = self.http.get(f"{prov_url}/prov/events?limit=200", headers=svc_headers) or {}
            graph = events.get("@graph") or []
            event_types.update(
                str(item.get("@type", "")).removeprefix("ds:")
                for item in graph
                if isinstance(item, dict)
            )
        missing = sorted(REQUIRED_PROVENANCE_EVENTS - event_types)
        if missing:
            result.fail_step("provenance complete", "missing event types", missing=missing)
            return result
        result.pass_step("provenance complete", "required lifecycle events present", observed=sorted(event_types))

        return result

    def _check_health(self, result: FlowResult) -> bool:
        s = self.settings
        services = [
            ("provider connector", s.connector_url),
            ("consumer connector", s.consumer_connector_url),
            ("dataset-api", s.dataset_api_url),
            ("provider provenance", s.provenance_url),
            ("consumer provenance", s.consumer_provenance_url),
        ]
        for name, url in services:
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step("health", f"{name} unreachable: {exc}")
                return False
        result.pass_step("health", "all services reachable")
        return True

    def _fetch_credentials(
        self, result: FlowResult, svc_headers: dict[str, str]
    ) -> tuple[str | None, str | None]:
        s = self.settings
        try:
            consumer_vc = self._resolve_user_vc(s.consumer_email, svc_headers)
            subject_vc = self._resolve_user_vc(s.data_subject_email, svc_headers)
            return consumer_vc, subject_vc
        except Exception as exc:
            result.fail_step("load credentials", str(exc))
            return None, None

    def _resolve_user_vc(self, email: str, headers: dict[str, str]) -> str:
        s = self.settings
        encoded_email = urllib.parse.quote(email, safe="")
        resp = self.http.get(
            f"{s.identity_registry_url}/users/resolve?email={encoded_email}",
            headers=headers,
        ) or {}
        vc_jws = resp.get("vc_jws") or ""
        if not vc_jws:
            raise RuntimeError(f"No VC found for user {email}")
        return vc_jws

    def _select_dataset(self, catalog: dict[str, Any]) -> dict[str, Any] | None:
        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        datasets = [item for item in datasets if isinstance(item, dict)]

        for ds in datasets:
            if ds.get("@id") == self.settings.asset_id or ds.get("id") == self.settings.asset_id:
                return ds
        for ds in datasets:
            ds_id = str(ds.get("@id") or ds.get("id") or "")
            if "meters_15m" in ds_id or "hourly" in ds_id:
                return ds
        for ds in datasets:
            if self._policy_requires_consent(self._policy(ds)):
                return ds
        return datasets[0] if datasets else None

    def _policy(self, dataset: dict[str, Any]) -> dict[str, Any]:
        policies = dataset.get("hasPolicy") or dataset.get("odrl:hasPolicy") or []
        if isinstance(policies, dict):
            return policies
        if isinstance(policies, list) and policies and isinstance(policies[0], dict):
            return policies[0]
        return {}

    def _policy_requires_consent(self, policy: dict[str, Any]) -> bool:
        return "ds:consentStatus" in json.dumps(policy)
