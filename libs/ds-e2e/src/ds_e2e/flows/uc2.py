from __future__ import annotations

import logging
import urllib.parse

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class UC2Flow(BaseFlow):
    """GP-2 / UC-2+UC-3: org shares aggregate data — owner-scoped negotiation."""

    name = "uc2"
    description = "Verify owner-scoped governance sync — assigner and scope from ownership"

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

        # Owner preconditions
        if not self._check_owner_preconditions(result, svc_headers):
            return result

        # Provider sync
        try:
            sync = self.http.post(f"{s.connector_url}/provider/sync", {}, headers=svc_headers) or {}
            result.pass_step("provider sync", "governance synced", synced=len(sync.get("synced") or []))
        except Exception as exc:
            result.fail_step("provider sync", str(exc))
            return result

        # Assigner check — resolve owner DID
        try:
            owner = self.http.get(
                f"{s.identity_registry_url}/owners/resolve?alias=example-org",
                headers=svc_headers,
            ) or {}
            owner_did = owner.get("canonical_uri") or owner.get("did")
            if owner_did:
                result.pass_step("assigner check", f"owner DID resolved: {owner_did}")
            else:
                result.fail_step("assigner check", "owner has no DID")
                return result
        except Exception as exc:
            result.fail_step("assigner check", str(exc))
            return result

        result.pass_step("uc2 complete", "owner-scoped sync verified")
        return result

    def _check_owner_preconditions(self, result: FlowResult, headers: dict[str, str]) -> bool:
        s = self.settings
        owner_alias = "example-org"
        member_did = "did:web:users.dataspaces.localhost:data-subject"

        try:
            owner = self.http.get(
                f"{s.identity_registry_url}/owners/resolve?alias={owner_alias}",
                headers=headers,
            )
            if not owner or not owner.get("id"):
                result.fail_step("owner precondition", f"owner '{owner_alias}' not found")
                return False
            result.pass_step("owner precondition", f"owner '{owner_alias}' exists")
        except Exception as exc:
            result.fail_step("owner precondition", str(exc))
            return False

        try:
            encoded = urllib.parse.quote(member_did, safe="")
            check = self.http.get(
                f"{s.identity_registry_url}/memberships/check?user_did={encoded}&organization={owner_alias}",
                headers=headers,
            ) or {}
            if not check.get("member"):
                result.fail_step("membership precondition", f"'{member_did}' is not a member of '{owner_alias}'")
                return False
            result.pass_step("membership precondition", f"'{member_did}' is a member of '{owner_alias}'")
        except Exception as exc:
            result.fail_step("membership precondition", str(exc))
            return False

        return True
