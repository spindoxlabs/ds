from __future__ import annotations

import logging

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class UC3Flow(BaseFlow):
    """GP-3 / UC-4: open/external data — no membership constraint."""

    name = "uc3"
    description = "Verify open-data owner resolution — no membership constraint applies"

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        # Health
        try:
            self.http.get(f"{s.connector_url}/health")
            result.pass_step("health", "connector reachable")
        except Exception as exc:
            result.fail_step("health", str(exc))
            return result

        # Service token
        try:
            self.http.acquire_service_token()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        svc_headers = self.http.bearer_headers()

        # Open-data owner resolution
        try:
            owner = self.http.get(
                f"{s.identity_registry_url}/owners/resolve?alias=open-data-provider",
                headers=svc_headers,
            ) or {}
            canonical = owner.get("canonical_uri")
            if canonical and not canonical.startswith("did:"):
                result.pass_step("open-data owner", f"URL-only owner resolved: {canonical}")
            elif canonical:
                result.pass_step("open-data owner", f"owner resolved (has DID): {canonical}")
            else:
                result.fail_step("open-data owner", "open-data-provider not found in registry")
                return result
        except Exception as exc:
            result.fail_step("open-data owner", str(exc))
            return result

        result.pass_step("uc3 complete", "open-data owner resolved — no membership constraint applies")
        return result
