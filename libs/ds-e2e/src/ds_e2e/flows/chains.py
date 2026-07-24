"""The three delegation chains.

Each chain is a different answer to "who is asking, in what capacity, and for
whose data" — and each fails in a different way if the boundary is not enforced.

    1. community  →  members  →  grid operator (measurements)
       The community is the controller. Its members consent for their own data.
       The boundary is the **subject pool**: a person who is not a member of the
       community cannot be swept into its consent.

    2. community → partner → members → grid operator (measurements)
       A third party joins. If it is a *processor* of the community it is
       disclosed under the DPA and asking again would be wrong. If it decides
       its own purposes it is an *independent controller* and consent to the
       community never reached it. The boundary is **capacity**, and capacity is
       read from what the organisation signed — never inferred.

    3. grid operator (operations) → community → members → grid operator (metering)
       One legal entity, two controllers. Metering holds the readings;
       operations wants them. Unbundling makes them distinct controllers, so the
       boundary is **controller_role**: a consent naming one does not reach the
       other, even though the legal entity is identical.

Run `ds-e2e scenario apply` first — these flows assert against fixtures rather
than creating them, so a missing fixture is reported as a missing precondition
instead of being silently invented mid-test.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

COMMUNITY_ALIAS = "example-org"
PARTNER_ALIAS = "partner-org"
OUTSIDER_ALIAS = "outsider-org"
GRID_ALIAS = "grid-operator"

PARTNER_DID = "did:web:partner.dataspaces.localhost"
OUTSIDER_DID = "did:web:outsider.dataspaces.localhost"
GRID_DID = "did:web:grid-operator.dataspaces.localhost"

GRID_OFFER = "grid-operations-planning"
GRID_PURPOSE = "EnergyCommunityOperation"


class _ChainFlow(BaseFlow):
    """Shared plumbing: tokens, credentials, consent checks, fixture guards."""

    def _service_headers(self, result: FlowResult) -> dict[str, str] | None:
        try:
            return self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return None

    def _reachable(self, result: FlowResult, *services: tuple[str, str]) -> bool:
        for name, url in services:
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step("health", f"{name} unreachable: {exc}")
                return False
        result.pass_step("health", f"{', '.join(n for n, _ in services)} reachable")
        return True

    def _require_owner(
        self, result: FlowResult, alias: str, headers: dict[str, str], step: str
    ) -> dict[str, Any] | None:
        """A missing fixture is a precondition failure, never a silent skip."""
        status, payload = self.http.raw(
            "GET",
            f"{self.settings.identity_registry_url}/owners/resolve?"
            f"alias={urllib.parse.quote(alias)}",
            headers=headers,
        )
        if status != 200 or not isinstance(payload, dict):
            result.fail_step(
                step,
                f"fixture organisation {alias!r} is not registered — "
                "run `ds-e2e scenario apply`",
                status_code=status,
            )
            return None
        return payload

    def _consent_check(
        self,
        headers: dict[str, str],
        *,
        consumer_id: str,
        subject_id: str,
        purpose: str,
        controller_role: str | None = None,
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "dataset_id": dataset_id or self.settings.asset_id,
            "consumer_id": consumer_id,
            "subject_id": subject_id,
            "purpose": purpose,
        }
        if controller_role:
            params["controller_role"] = controller_role
        return self.http.get(
            f"{self.settings.connector_url}/internal/consent/check?"
            + urllib.parse.urlencode(params),
            headers=headers,
        ) or {}

    def _resolve_user_vc(self, email: str, headers: dict[str, str]) -> str:
        encoded = urllib.parse.quote(email, safe="")
        resp = self.http.get(
            f"{self.settings.identity_registry_url}/users/resolve?email={encoded}",
            headers=headers,
        ) or {}
        vc_jws = resp.get("vc_jws") or ""
        if not vc_jws:
            raise RuntimeError(f"No VC found for user {email}")
        return vc_jws

    def _subject_headers(self, result: FlowResult, svc: dict[str, str]) -> dict[str, str] | None:
        s = self.settings
        try:
            return {
                "X-Subject-Id": s.data_subject_id,
                "X-User-VC": self._resolve_user_vc(s.data_subject_email, svc),
            }
        except Exception as exc:
            result.fail_step("load credentials", str(exc))
            return None

    def _revoke_share(
        self, headers: dict[str, str], offer_id: str, consumer_id: str | None = None
    ) -> None:
        """Leave no standing grant behind — the next flow must start from zero.

        ``consumer_id`` must match the grant. A consent row is keyed by
        ``(subject, dataset, consumer)``, so omitting it here falls back to the
        default consumer DID and withdraws a *different* row — the original grant
        survives, and the flow that granted to a named third party (the grid
        operator, in the unbundling chain) then reports its own consent as
        surviving its own withdrawal.
        """
        body: dict[str, object] = {"offer_id": offer_id, "enabled": False}
        if consumer_id:
            body["consumer_id"] = consumer_id
        self.http.raw(
            "POST",
            f"{self.settings.connector_url}/consent/my/shares",
            body=body,
            headers=headers,
        )


# ── Chain 1 ──────────────────────────────────────────────────────────────────


class ChainCommunityFlow(_ChainFlow):
    """Community → members → grid operator (measurements)."""

    name = "chain-community"
    description = (
        "Community-mediated consent: a member consents for their own data, and "
        "the community's subject pool bounds who can be asked"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        if not self._reachable(
            result,
            ("connector", s.connector_url),
            ("identity-registry", s.identity_registry_url),
        ):
            return result

        svc = self._service_headers(result)
        if svc is None:
            return result

        # 1. The community exists and the member is in its pool.
        if self._require_owner(result, COMMUNITY_ALIAS, svc, "community fixture") is None:
            return result

        member_check = self.http.get(
            f"{s.identity_registry_url}/memberships/check?"
            f"user_did={urllib.parse.quote(s.data_subject_id, safe='')}"
            f"&organization={COMMUNITY_ALIAS}",
            headers=svc,
        ) or {}
        if not member_check.get("member"):
            result.fail_step(
                "subject pool",
                f"{s.data_subject_id} is not a member of {COMMUNITY_ALIAS} — "
                "the consent below would be out of pool",
            )
            return result
        result.pass_step(
            "subject pool", f"the data subject is in {COMMUNITY_ALIAS}'s member pool"
        )

        subject = self._subject_headers(result, svc)
        if subject is None:
            return result

        # 2. The member consents, and the row is stamped with the community as
        #    controller — the consent names who decides the purpose, not merely
        #    which connector will pull.
        try:
            rows = self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {"offer_id": s.sharing_offer_id, "consumer_id": s.consumer_did, "enabled": True},
                headers=subject,
            ) or []
        except Exception as exc:
            result.fail_step("member consents", str(exc))
            return result
        rows = rows if isinstance(rows, list) else [rows]
        controllers = {r.get("controller") for r in rows}
        if controllers != {COMMUNITY_ALIAS}:
            result.fail_step(
                "member consents",
                "the consent row does not name the community as controller",
                controllers=sorted(str(c) for c in controllers),
            )
            return result
        result.pass_step(
            "member consents",
            "the member's consent is stamped with the community as controller",
            rows=len(rows),
        )

        # 3. It authorises the declared purpose, and nothing wider.
        active = self._consent_check(
            svc,
            consumer_id=s.consumer_did,
            subject_id=s.data_subject_id,
            purpose=s.consented_purpose,
        )
        if not active.get("consent_active"):
            result.fail_step(
                "consent authorises", "the consent did not authorise its own purpose",
                reason=active.get("reason"),
            )
            self._revoke_share(subject, s.sharing_offer_id)
            return result

        wider = self._consent_check(
            svc,
            consumer_id=s.consumer_did,
            subject_id=s.data_subject_id,
            purpose=s.unconsented_purpose,
        )
        if wider.get("consent_active"):
            result.fail_step(
                "consent authorises",
                "the consent reached a purpose the member never agreed to",
                purpose=s.unconsented_purpose,
            )
            self._revoke_share(subject, s.sharing_offer_id)
            return result
        result.pass_step(
            "consent authorises",
            "the member's consent covers its purpose and no other",
            purpose=s.consented_purpose,
        )

        # 4. The pool is a boundary, not a label. A subject outside the community
        #    must not be reachable through it — this is the assertion that makes
        #    delegated consent safe, and the one nothing previously covered.
        outsider = "did:web:users.dataspaces.localhost:outsider"
        out_check = self.http.get(
            f"{s.identity_registry_url}/memberships/check?"
            f"user_did={urllib.parse.quote(outsider, safe='')}"
            f"&organization={COMMUNITY_ALIAS}",
            headers=svc,
        ) or {}
        if out_check.get("member"):
            result.fail_step("pool is a boundary", f"{outsider} is unexpectedly a member")
            self._revoke_share(subject, s.sharing_offer_id)
            return result

        status, body = self.http.raw(
            "POST",
            f"{s.connector_url}/consent/request",
            body={
                "consumer_id": s.consumer_did,
                "dataset_id": s.asset_id,
                "subject_ids": [outsider],
                "purpose": [s.consented_purpose],
                "offer_id": s.sharing_offer_id,
            },
            headers=svc,
        )
        if status < 400:
            result.fail_step(
                "pool is a boundary",
                "a consent request was accepted for a subject outside the community pool",
                status_code=status,
                response=body,
            )
            self._revoke_share(subject, s.sharing_offer_id)
            return result
        result.pass_step(
            "pool is a boundary",
            "a subject outside the community cannot be drawn into its consent",
            refused_with=status,
        )

        # 5. Leave nothing standing.
        self._revoke_share(subject, s.sharing_offer_id)
        after = self._consent_check(
            svc,
            consumer_id=s.consumer_did,
            subject_id=s.data_subject_id,
            purpose=s.consented_purpose,
        )
        if after.get("consent_active"):
            result.fail_step(
                "withdrawal", "the consent survived its own withdrawal"
            )
            return result
        result.pass_step("withdrawal", "withdrawing the share closes the check again")
        return result


# ── Chain 2 ──────────────────────────────────────────────────────────────────


class ChainPartnerFlow(_ChainFlow):
    """Community → partner → members → grid operator (measurements)."""

    name = "chain-partner"
    description = (
        "Capacity decides the consent boundary: a processor of the controller is "
        "disclosed, an independent controller must be asked"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        if not self._reachable(
            result,
            ("connector", s.connector_url),
            ("identity-registry", s.identity_registry_url),
        ):
            return result

        svc = self._service_headers(result)
        if svc is None:
            return result

        for alias in (PARTNER_ALIAS, OUTSIDER_ALIAS):
            if self._require_owner(result, alias, svc, "partner fixtures") is None:
                return result
        result.pass_step("partner fixtures", "partner and outsider organisations are registered")

        # 1. Capacity must be *readable*. This is the endpoint the connector's
        #    circle check calls; if it cannot answer, every party silently
        #    resolves to "outside", and the processor-disclosure path — the whole
        #    point of the DPA — can never fire.
        capacities: dict[str, str] = {}
        for alias, did, expected in (
            (PARTNER_ALIAS, PARTNER_DID, "processor"),
            (OUTSIDER_ALIAS, OUTSIDER_DID, "independent_controller"),
        ):
            status, payload = self.http.raw(
                "GET",
                f"{s.identity_registry_url}/agreements/current?"
                f"participant_did={urllib.parse.quote(did, safe='')}",
                headers=svc,
            )
            if status != 200 or not isinstance(payload, dict):
                result.fail_step(
                    "capacity is resolvable",
                    f"no current agreement resolves for {alias} — the circle check "
                    "would treat every party as outside",
                    status_code=status,
                    participant=did,
                )
                return result
            capacities[alias] = str(payload.get("capacity"))
            if capacities[alias] != expected:
                result.fail_step(
                    "capacity is resolvable",
                    f"{alias} declares capacity {capacities[alias]!r}, "
                    f"scenario expects {expected!r}",
                )
                return result
        result.pass_step(
            "capacity is resolvable",
            "each organisation's signed capacity is readable and distinct",
            **capacities,
        )

        # 2. Capacity is read, never inferred. An organisation with no accepted
        #    agreement must not default to the permissive answer.
        status, _ = self.http.raw(
            "GET",
            f"{s.identity_registry_url}/agreements/current?"
            f"participant_did={urllib.parse.quote('did:web:unsigned.dataspaces.localhost', safe='')}",
            headers=svc,
        )
        if status == 200:
            result.fail_step(
                "unsigned party has no capacity",
                "a participant that signed nothing was given a capacity",
            )
            return result
        result.pass_step(
            "unsigned party has no capacity",
            "a party with no accepted agreement resolves to no capacity, so the "
            "circle check falls outside and asks",
            refused_with=status,
        )

        # 3. The processor half: membership is the offer's admitted_by
        #    constraint, and capacity alone is not enough to be inside.
        member = self.http.get(
            f"{s.identity_registry_url}/memberships/check?"
            f"user_did={urllib.parse.quote(PARTNER_DID, safe='')}"
            f"&organization={COMMUNITY_ALIAS}",
            headers=svc,
        ) or {}
        outsider_member = self.http.get(
            f"{s.identity_registry_url}/memberships/check?"
            f"user_did={urllib.parse.quote(OUTSIDER_DID, safe='')}"
            f"&organization={COMMUNITY_ALIAS}",
            headers=svc,
        ) or {}
        if not member.get("member"):
            result.fail_step(
                "admitted_by is checkable",
                f"{PARTNER_ALIAS} is not a member of {COMMUNITY_ALIAS} — it cannot "
                "satisfy the offer's processor category",
            )
            return result
        if outsider_member.get("member"):
            result.fail_step(
                "admitted_by is checkable",
                f"{OUTSIDER_ALIAS} is a member of {COMMUNITY_ALIAS}; the scenario "
                "requires it to fail both halves of the circle definition",
            )
            return result
        result.pass_step(
            "admitted_by is checkable",
            "the partner satisfies the offer's processor category and the outsider does not",
        )

        # 4. The consequence. A standing consent naming the community as
        #    controller must not, by itself, authorise a party that decides its
        #    own purposes — regardless of it holding a valid agreement.
        subject = self._subject_headers(result, svc)
        if subject is None:
            return result

        try:
            self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {"offer_id": s.sharing_offer_id, "consumer_id": s.consumer_did, "enabled": True},
                headers=subject,
            )
        except Exception as exc:
            result.fail_step("member consents", str(exc))
            return result

        outsider_check = self._consent_check(
            svc,
            consumer_id=OUTSIDER_DID,
            subject_id=s.data_subject_id,
            purpose=s.consented_purpose,
        )
        if outsider_check.get("consent_active"):
            result.fail_step(
                "independent controller is not covered",
                "a party that decides its own purposes was authorised by a consent "
                "given to a different controller",
                consumer=OUTSIDER_DID,
            )
            self._revoke_share(subject, s.sharing_offer_id)
            return result
        result.pass_step(
            "independent controller is not covered",
            "consent to the community does not reach an independent controller",
            reason=outsider_check.get("reason"),
        )

        self._revoke_share(subject, s.sharing_offer_id)
        result.pass_step("cleanup", "standing share withdrawn")
        return result


# ── Chain 3 ──────────────────────────────────────────────────────────────────


class ChainUnbundlingFlow(_ChainFlow):
    """Grid operator (operations) → community → members → grid operator (metering)."""

    name = "chain-unbundling"
    description = (
        "One legal entity, two controllers: a consent naming the operations role "
        "must not authorise the metering role"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        if not self._reachable(
            result,
            ("connector", s.connector_url),
            ("identity-registry", s.identity_registry_url),
        ):
            return result

        svc = self._service_headers(result)
        if svc is None:
            return result

        if self._require_owner(result, GRID_ALIAS, svc, "grid operator fixture") is None:
            return result

        # 1. The offer must actually declare a role. Without it there is no
        #    boundary to test, and the flow would pass by asserting nothing.
        offers = self.http.get(f"{s.connector_url}/ns/sharing-offers") or []
        offer = next((o for o in offers if o.get("id") == GRID_OFFER), None)
        if offer is None:
            result.fail_step(
                "role-scoped offer",
                f"offer {GRID_OFFER!r} is not published — add it to "
                "services/connector/governance/sharing-offers.yaml and reload the connector",
                available=[o.get("id") for o in offers],
            )
            return result
        recipients = offer.get("recipients") or {}
        if recipients.get("controller_role") != "operations":
            result.fail_step(
                "role-scoped offer",
                "the offer does not name a controller role, so the unbundling "
                "boundary is not expressed",
                controller_role=recipients.get("controller_role"),
            )
            return result
        result.pass_step(
            "role-scoped offer",
            "the offer names one role of the controller, not just the legal entity",
            controller=recipients.get("controller"),
            controller_role=recipients.get("controller_role"),
        )

        subject = self._subject_headers(result, svc)
        if subject is None:
            return result

        # 2. Consenting to it stamps the role onto the row.
        try:
            rows = self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {"offer_id": GRID_OFFER, "consumer_id": GRID_DID, "enabled": True},
                headers=subject,
            ) or []
        except Exception as exc:
            result.fail_step("member consents to a role", str(exc))
            return result
        rows = rows if isinstance(rows, list) else [rows]
        roles = {r.get("controller_role") for r in rows}
        if roles != {"operations"}:
            result.fail_step(
                "member consents to a role",
                "the consent row did not record which role was consented to",
                controller_role=sorted(str(r) for r in roles),
            )
            self._revoke_share(subject, GRID_OFFER, consumer_id=GRID_DID)
            return result
        result.pass_step(
            "member consents to a role",
            "the consent row records the controller role, not only the controller",
            controller_role="operations",
        )

        # 3. The consented role is authorised.
        allowed = self._consent_check(
            svc,
            consumer_id=GRID_DID,
            subject_id=s.data_subject_id,
            purpose=GRID_PURPOSE,
            controller_role="operations",
        )
        if not allowed.get("consent_active"):
            result.fail_step(
                "consented role is authorised",
                "the role the member consented to was refused",
                reason=allowed.get("reason"),
            )
            self._revoke_share(subject, GRID_OFFER, consumer_id=GRID_DID)
            return result
        result.pass_step(
            "consented role is authorised",
            "a request in the consented role is allowed",
            controller_role="operations",
        )

        # 4. The other role of the same legal entity is not. This is the
        #    unbundling assertion: same participant DID, same purpose, same
        #    subject — only the role differs, and that must be enough to refuse.
        other = self._consent_check(
            svc,
            consumer_id=GRID_DID,
            subject_id=s.data_subject_id,
            purpose=GRID_PURPOSE,
            controller_role="metering",
        )
        if other.get("consent_active"):
            result.fail_step(
                "other role is refused",
                "a consent given to the operations role also authorised the "
                "metering role of the same legal entity",
                controller_role="metering",
            )
            self._revoke_share(subject, GRID_OFFER, consumer_id=GRID_DID)
            return result
        result.pass_step(
            "other role is refused",
            "the second controller of the same legal entity is not covered",
            controller_role="metering",
            reason=other.get("reason"),
        )

        # 5. Withdrawal, and no residue for the next run.
        self._revoke_share(subject, GRID_OFFER, consumer_id=GRID_DID)
        after = self._consent_check(
            svc,
            consumer_id=GRID_DID,
            subject_id=s.data_subject_id,
            purpose=GRID_PURPOSE,
            controller_role="operations",
        )
        if after.get("consent_active"):
            result.fail_step("withdrawal", "the role-scoped consent survived withdrawal")
            return result
        result.pass_step("withdrawal", "withdrawing closes the role-scoped consent")
        return result
