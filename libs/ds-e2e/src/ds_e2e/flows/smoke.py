from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any

from ds_e2e.consent import legal_basis
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
    rules = ("C-1", "X-1", "X-3", "X-4", "X-5")

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

        # 6. Consent grant — by sharing offer, not by dataset.
        #    The connector expands the offer into per-dataset rows and stamps
        #    the purpose and controller from it, so the decision cannot drift
        #    from the copy the person read.
        try:
            offers = self.http.get(f"{s.connector_url}/ns/sharing-offers") or []
            offer = next(
                (o for o in offers if o.get("id") == s.sharing_offer_id),
                None,
            )
            if offer is None:
                result.fail_step(
                    "sharing offers",
                    f"offer '{s.sharing_offer_id}' not published",
                    available=[o.get("id") for o in offers],
                )
                return result
            if not offer.get("requires_consent"):
                result.fail_step(
                    "sharing offers",
                    f"offer '{s.sharing_offer_id}' is not consent-based",
                    legal_basis=offer.get("legal_basis"),
                )
                return result
            result.pass_step(
                "sharing offers",
                "public offer vocabulary served",
                offer=offer.get("id"),
                purpose=offer.get("purpose"),
                controller=offer.get("recipients", {}).get("controller"),
            )
        except Exception as exc:
            result.fail_step("sharing offers", str(exc))
            return result

        try:
            share_body = {
                "offer_id": s.sharing_offer_id,
                "consumer_id": s.consumer_did,
                "enabled": True,
            }
            share = self.http.post(
                f"{s.connector_url}/consent/my/shares", share_body, headers=subject_headers
            ) or []
            rows = share if isinstance(share, list) else [share]
            if not rows or any(r.get("purpose") != [s.consented_purpose] for r in rows):
                result.fail_step(
                    "consent grant", "offer did not expand to purpose-stamped rows", rows=rows
                )
                return result
            result.pass_step(
                "consent grant",
                "data subject granted standing data sharing for one purpose",
                consent_ids=[r.get("id") for r in rows],
                purpose=s.consented_purpose,
            )
        except Exception as exc:
            result.fail_step("consent grant", str(exc))
            return result

        # 6b. The scoped wildcard (§3.1). A consent provisioned by an operator on
        #     the subject's behalf (POST /consent/admin/shares, the path the
        #     onboarding service uses) carries consumer_id = "*": it admits any
        #     party inside the circle for this controller and purpose. A consumer
        #     with no row of its own must be authorised by that wildcard alone,
        #     and never for a purpose the subject did not consent to.
        try:
            wildcard_rows = self.http.post(
                f"{s.connector_url}/consent/admin/shares",
                {
                    "subject_id": s.data_subject_id,
                    "offer_id": s.sharing_offer_id,
                    "enabled": True,
                    "legal_basis": legal_basis("e2e-verification"),
                },
                headers=svc_headers,
            ) or []
            wildcard_rows = wildcard_rows if isinstance(wildcard_rows, list) else [wildcard_rows]
            if not wildcard_rows or any(r.get("consumer_id") != "*" for r in wildcard_rows):
                result.fail_step(
                    "wildcard consent",
                    "admin provisioning did not create wildcard-scoped rows",
                    rows=wildcard_rows,
                )
                return result
        except HttpError as exc:
            result.fail_step("wildcard consent", f"HTTP {exc.status}", response=exc.body)
            return result

        novel_consumer = "did:web:novel.dataspaces.localhost"
        wildcard_check = self.http.get(
            f"{s.connector_url}/internal/consent/check?"
            + urllib.parse.urlencode(
                {
                    "dataset_id": s.asset_id,
                    "consumer_id": novel_consumer,
                    "subject_id": s.data_subject_id,
                    "purpose": s.consented_purpose,
                }
            ),
            headers=svc_headers,
        ) or {}
        if not wildcard_check.get("consent_active"):
            result.fail_step(
                "wildcard consent",
                "a consumer with no specific row was not authorised by the wildcard",
                reason=wildcard_check.get("reason"),
            )
            return result
        result.pass_step(
            "wildcard consent",
            "operator-provisioned wildcard authorises any in-circle consumer for the consented purpose",
            wildcard_datasets=[r.get("dataset_id") for r in wildcard_rows],
            novel_consumer=novel_consumer,
        )

        # 7. Negotiate
        policy = self._policy(dataset)
        offer_id = str(policy.get("@id") or f"{asset_id}#offer")
        # Declare an intent, so the round trip covers the accountability record
        # and not only the protocol. The purpose is taken from the offer itself:
        # the connector refuses anything the offer does not permit, so a
        # hardcoded one would make this flow depend on the dev catalogue.
        offer_purposes = self._offer_purposes(policy)
        # Declare the purpose this subject actually consented to. Declaring any
        # other permitted purpose is legitimate and would be *correctly* refused
        # at query time for want of consent — a real scenario, but not this one.
        declared_purpose = [
            p for p in offer_purposes if p.rsplit("/", 1)[-1] == s.consented_purpose
        ] or offer_purposes[:1]
        negotiate_body = {
            "counter_party_address": s.counter_party_address,
            "offer_id": offer_id,
            "asset_id": asset_id,
            "assigner": s.provider_did,
            "odrl_policy": policy or None,
            "declared_purpose": declared_purpose,
            "justification_ref": "e2e-smoke",
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

        # The declaration must survive to the record, or it was never evidence.
        if declared_purpose:
            requests = self.http.get(
                f"{s.consumer_connector_url}/consumer/requests",
                headers=consumer_headers,
            ) or []
            recorded = next(
                (r for r in requests if r.get("negotiation_id") == negotiation_id), None
            )
            stated = (recorded or {}).get("declared_purpose") or []
            expected = {p.rsplit("/", 1)[-1] for p in declared_purpose}
            if not recorded:
                result.fail_step("declared purpose", "no access request recorded")
                return result
            if set(stated) != expected:
                result.fail_step(
                    "declared purpose",
                    "the request record does not carry the declared purpose",
                    declared=sorted(expected),
                    recorded=sorted(stated),
                )
                return result
            result.pass_step(
                "declared purpose",
                "stated intent is recorded against the request",
                purpose=sorted(stated),
                justification_ref=(recorded or {}).get("justification_ref"),
            )

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

        # 11. Query the data plane the way a real client does.
        #
        # No exchange identifiers as parameters: the EDR token proves who is
        # asking, three `Edc-*` headers name the exchange, and the query itself
        # names the dataset. This is the contract the production dataset-api
        # implements — a probe shaped any other way would validate a mock.
        edr = self.http.get(
            f"{s.consumer_connector_url}/consumer/edr/{encoded_transfer_id}",
            headers=consumer_headers,
        ) or {}
        edr_token = str(edr.get("authorization") or "")
        # The **shared** DSP agreement id, which the connector resolves for us.
        # `contractAgreementId` from the negotiation is this side's *local* id
        # and means nothing to the provider — EDC keeps the two apart, and a
        # client that sends the wrong one is refused as `agreement_unknown`.
        shared_agreement_id = str(edr.get("agreement_id") or agreement_id)
        if not edr_token:
            result.fail_step("query with consent", "EDR carries no authorization token")
            return result

        def data_query(purpose: str | None, url: str | None = None) -> tuple[int, Any]:
            headers = {
                "Authorization": edr_token,
                "Edc-Contract-Agreement-Id": shared_agreement_id,
                "Edc-Transfer-Process-Id": transfer_id,
            }
            if purpose:
                headers["Edc-Purpose"] = purpose
            return self.http.post_raw(
                f"{url or s.dataset_api_url}/query",
                {"sql": f"SELECT * FROM {asset_id}", "limit": 100},
                headers=headers,
            )

        # 11. **Both data planes, with the one credential** (`T-1`).
        #
        # The query surface has two implementations — `services/dataset-api-mock`
        # and the real celine `dataset-api` — and a run used to exercise exactly
        # one while nothing in the output said which. A green suite against the
        # mock and a green suite against the real one are different evidence.
        #
        # One exchange covers both, measured rather than assumed: the same EDR is
        # accepted by both, because both verify the same bearer and both ask the
        # same connector's `/internal/dataplane/authorize`. So this is a loop, not
        # a second negotiation — and each backend is named in its own step, so a
        # plane that was not reached cannot hide inside a passing one.
        for label, url in s.data_planes:
            status, query_payload = data_query(s.consented_purpose, url)
            if (
                status != 200
                or not isinstance(query_payload, dict)
                or query_payload.get("count", 0) < 1
            ):
                result.fail_step(
                    "query with consent",
                    f"expected at least one authorized row from {label}",
                    status_code=status,
                    data_plane=label,
                )
                return result
            result.pass_step(
                "query with consent",
                f"consent and active transfer allow data query for the consented "
                f"purpose — {label}",
                rows=query_payload.get("count"),
                purpose=s.consented_purpose,
                data_plane=label,
            )

        # 11b. The purpose is binding, not decorative. The same agreement and
        #      the same active transfer must yield nothing for a purpose this
        #      subject never agreed to — ds refuses the request outright rather
        #      than returning rows it should not.
        # **Refusals on every plane, not just the configured one.** A refusal is
        # the assertion most worth having on both: a data plane that *serves* when
        # it should refuse is the failure, and testing one implementation says
        # nothing about the other's enforcement.
        for label, url in s.data_planes:
            status, _ = data_query(s.unconsented_purpose, url)
            if status != 403:
                result.fail_step(
                    "query for an unconsented purpose",
                    f"expected a refusal for an unconsented purpose — {label}",
                    status_code=status,
                    data_plane=label,
                )
                return result
        result.pass_step(
            "query for an unconsented purpose",
            "a purpose the subject did not consent to is refused by every data plane",
            purpose=s.unconsented_purpose,
            data_planes=[label for label, _ in s.data_planes],
        )

        # 11c. Omitting the purpose entirely must not behave like a wildcard.
        for label, url in s.data_planes:
            status, _ = data_query(None, url)
            if status != 403:
                result.fail_step(
                    "query without a purpose",
                    f"an undeclared purpose did not fail closed — {label}",
                    status_code=status,
                    data_plane=label,
                )
                return result
        result.pass_step(
            "query without a purpose",
            "an undeclared purpose fails closed on a consent-required dataset, on "
            "every data plane",
            data_planes=[label for label, _ in s.data_planes],
        )

        # 11d. The agreement is bound to the consumer the token proves. Naming a
        #      different agreement must not read its data — this is what makes a
        #      self-asserted header safe.
        status, _ = self.http.post_raw(
            f"{s.dataset_api_url}/query",
            {"sql": f"SELECT * FROM {asset_id}", "limit": 100},
            headers={
                "Authorization": edr_token,
                "Edc-Contract-Agreement-Id": "not-your-agreement",
                "Edc-Purpose": s.consented_purpose,
            },
        )
        if status != 403:
            result.fail_step(
                "foreign agreement refused",
                "an unknown agreement id was not refused",
                status_code=status,
            )
            return result
        result.pass_step(
            "foreign agreement refused",
            "an agreement the caller does not hold yields no data",
        )

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
            blocked_status, _ = data_query(s.consented_purpose)
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
