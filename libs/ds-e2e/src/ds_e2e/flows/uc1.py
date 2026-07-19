from __future__ import annotations

import logging
import urllib.parse

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class UC1Flow(BaseFlow):
    """GP-1 / UC-1: delegated consent with subject-pool validation."""

    name = "uc1"
    description = "Verify subject-pool preconditions: in-org and out-of-org subjects"

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

        # Owner precondition
        if not self._check_owner_preconditions(result, svc_headers):
            return result

        # Non-member check
        non_member_did = "did:web:users.dataspaces.localhost:outsider"
        try:
            encoded = urllib.parse.quote(non_member_did, safe="")
            check = self.http.get(
                f"{s.identity_registry_url}/memberships/check?user_did={encoded}&organization=example-org",
                headers=svc_headers,
            ) or {}
            if check.get("member"):
                result.fail_step("non-member precondition", f"'{non_member_did}' is unexpectedly a member")
                return result
            result.pass_step("non-member precondition", f"'{non_member_did}' confirmed not a member")
        except Exception as exc:
            result.fail_step("non-member precondition", str(exc))
            return result

        result.pass_step("uc1 complete", "subject-pool preconditions verified")
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
