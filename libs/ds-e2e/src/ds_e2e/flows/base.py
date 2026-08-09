from __future__ import annotations

import json
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


class BaseFlow(ABC):
    name: str
    description: str

    def __init__(self, settings: E2ESettings, http: HttpClient):
        self.settings = settings
        self.http = http

    @abstractmethod
    def execute(self) -> FlowResult: ...

    def cleanup(self) -> None:
        """Restore whatever this flow changed outside its own records.

        `runner.run_flow` calls this in a `finally` for **every** flow, so it
        runs on the exception path as well as the happy one. Override it when a
        flow mutates the stack itself — `fail-closed` stops a container — and
        make it idempotent: `execute` is expected to undo its own work too, so
        this is the net, not the primary path.
        """

    def _check_health(self, result: FlowResult) -> bool:
        """Every service a data-exchange flow touches, before it touches one.

        On `BaseFlow` because `E2E-14` is what happens without it: one
        unreachable service raised out of `run_all` and the run ended with a
        traceback and **zero** results instead of one legible failure.
        `api_contract` overrides it with a wider list — it probes more services
        than an exchange does.
        """
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

    # ── Reading a DSP catalogue ──────────────────────────────────────────────
    #
    # Here rather than on one flow because three already needed them and the
    # third copy was about to be written. `_policy` had **two** implementations
    # (`smoke`, `two_providers`) parsing the same JSON-LD two ways — the shape
    # `E2E-03` and `E2E-14` each had to undo, one level down.

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
            wanted = self.settings.asset_id
            if ds.get("@id") == wanted or ds.get("id") == wanted:
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

    def _offer_purposes(self, policy: dict[str, Any]) -> list[str]:
        """Every purpose IRI the offer permits.

        Reads the set-valued form as well as the scalar one: a multi-purpose
        dataset publishes one ``odrl:purpose`` constraint with ``odrl:isAnyOf``
        over a list, and a reader that only understands a scalar finds nothing
        on exactly those datasets.
        """
        purposes: list[str] = []
        operands = {"odrl:purpose", "purpose", "http://www.w3.org/ns/odrl/2/purpose"}

        def walk(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                left = value.get("odrl:leftOperand") or value.get("leftOperand")
                if isinstance(left, dict):
                    left = left.get("@id") or left.get("id")
                if left in operands:
                    right = value.get("odrl:rightOperand") or value.get("rightOperand")
                    for item in right if isinstance(right, list) else [right]:
                        if isinstance(item, dict):
                            item = item.get("@id") or item.get("@value")
                        if isinstance(item, str) and item not in purposes:
                            purposes.append(item)
                for item in value.values():
                    walk(item)

        walk(policy)
        return purposes
