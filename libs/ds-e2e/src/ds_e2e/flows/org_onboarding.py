from __future__ import annotations

import logging
import urllib.parse
import uuid

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class OrgOnboardingFlow(BaseFlow):
    """Block D §5.8 — organisation onboarding lifecycle.

    Drives the full admin path against the identity-registry:
    register → verify → agreement → issue-credential → promote, asserting each
    gate (issue-before-agreement and promote-before-credential both fail closed)
    and the resulting transaction-readiness (participant registered, did:web
    resolvable, OrganizationCredential active). Finishes with suspend, proving
    the StatusList bit and participant deactivation land in one step.

    A fresh unique alias is used per run so the negative-gate assertions never
    depend on prior state.

    The literal DSP pull by the new organisation is *not* exercised here: in the
    dev topology only the provider and consumer EDCs exist, so a brand-new
    participant has no connector of its own. A promoted org negotiates and pulls
    identically to any participant — that path is covered end to end by the
    `smoke` flow. This flow proves the org reaches transaction-ready state.
    """

    name = "org-onboarding"
    description = (
        "Organisation onboarding lifecycle: register → verify → agreement → "
        "credential → promote, with gate and readiness assertions"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        ir = s.identity_registry_url
        alias = f"{s.org_e2e_alias}-{uuid.uuid4().hex[:8]}"
        did = f"did:web:{alias}.dataspaces.localhost"
        dsp_address = f"http://{alias}.dataspaces.localhost/protocol"

        # 1. Health
        try:
            self.http.get(f"{ir}/health")
            result.pass_step("health", "identity-registry reachable")
        except Exception as exc:
            result.fail_step("health", str(exc))
            return result

        # 2. Admin token — org endpoints require identity-registry.admin, which
        #    the default portal service client does not hold.
        try:
            admin = self.http.bearer_headers_for(
                s.ir_admin_client_id, s.ir_admin_client_secret
            )
            result.pass_step("admin token", "acquired identity-registry.admin token")
        except Exception as exc:
            result.fail_step("admin token", str(exc))
            return result

        # 3. Agreement precondition (seeded via `ir-cli agreement import`)
        try:
            agreements = self.http.get(f"{ir}/agreements", headers=admin) or []
            match = next(
                (
                    a
                    for a in agreements
                    if a.get("id") == s.org_agreement_id
                    and a.get("version") == s.org_agreement_version
                ),
                None,
            )
            if not match:
                result.fail_step(
                    "agreement precondition",
                    f"agreement '{s.org_agreement_id}@{s.org_agreement_version}' "
                    "not seeded — run `ir-cli agreement import`",
                    available=[f"{a.get('id')}@{a.get('version')}" for a in agreements],
                )
                return result
            result.pass_step(
                "agreement precondition",
                "service agreement is seeded and served",
                capacity=match.get("capacity"),
            )
        except Exception as exc:
            result.fail_step("agreement precondition", str(exc))
            return result

        # 4. Register application
        try:
            app = self.http.post(
                f"{ir}/admin/organizations/applications",
                {
                    "alias": alias,
                    "legal_name": s.org_e2e_legal_name,
                    "registration_number": "IT-E2E-0001",
                    "registration_type": "vatID",
                    "hq_country_code": "IT-TN",
                    "legal_country_code": "IT-TN",
                    "roles": ["consumer"],
                    "did": did,
                    "dsp_address": dsp_address,
                },
                headers=admin,
            ) or {}
            application_id = app.get("id")
            if not application_id or app.get("status") != "pending":
                result.fail_step("register", "application not created as pending", app=app)
                return result
            result.pass_step("register", "organisation application created", alias=alias)
        except Exception as exc:
            result.fail_step("register", str(exc))
            return result

        # 5. Verify → promotes legal identity into an Owner row
        try:
            verified = self.http.patch(
                f"{ir}/admin/organizations/applications/{application_id}",
                {"status": "verified", "verified_by": "e2e-operator"},
                headers=admin,
            ) or {}
            if verified.get("status") != "verified":
                result.fail_step("verify", "application verification failed", body=verified)
                return result
            resolved = self.http.get(
                f"{ir}/owners/resolve?alias={urllib.parse.quote(alias)}", headers=admin
            ) or {}
            if resolved.get("status") != "verified":
                result.fail_step("verify", "owner not promoted to verified", owner=resolved)
                return result
            result.pass_step("verify", "application verified and owner promoted")
        except Exception as exc:
            result.fail_step("verify", str(exc))
            return result

        # 6. GATE — issuing a credential before any agreement is accepted must
        #    fail closed (§5.6).
        status, body = self.http.post_raw(
            f"{ir}/admin/credentials/organization",
            {"alias": alias, "roles": ["consumer"], "dsp_address": dsp_address},
            headers=admin,
        )
        if status == 201:
            result.fail_step(
                "gate: credential needs agreement",
                "credential issued with no accepted agreement",
            )
            return result
        result.pass_step(
            "gate: credential needs agreement",
            f"issue-credential refused before agreement (HTTP {status})",
        )

        # 7. Accept the agreement
        try:
            acceptance = self.http.post(
                f"{ir}/admin/owners/{urllib.parse.quote(alias)}/agreement",
                {
                    "agreement_id": s.org_agreement_id,
                    "version": s.org_agreement_version,
                    "locale": "en",
                    "accepted_by": "e2e-org-contact",
                },
                headers=admin,
            ) or {}
            if not acceptance.get("text_sha256"):
                result.fail_step("agreement", "acceptance missing text hash", body=acceptance)
                return result
            result.pass_step(
                "agreement",
                "organisation accepted the current agreement version",
                capacity=acceptance.get("capacity"),
            )
        except Exception as exc:
            result.fail_step("agreement", str(exc))
            return result

        # 8. GATE — promoting to a participant before a credential exists must
        #    fail closed (§5.6).
        status, _ = self.http.post_raw(
            f"{ir}/admin/owners/{urllib.parse.quote(alias)}/promote",
            {"dsp_address": dsp_address, "roles": ["consumer"]},
            headers=admin,
        )
        if status == 201:
            result.fail_step(
                "gate: promote needs credential",
                "participant promoted with no OrganizationCredential",
            )
            return result
        result.pass_step(
            "gate: promote needs credential",
            f"promote refused before a credential exists (HTTP {status})",
        )

        # 9. Issue the OrganizationCredential (now that the agreement is accepted)
        try:
            cred = self.http.post(
                f"{ir}/admin/credentials/organization",
                {"alias": alias, "roles": ["consumer"], "dsp_address": dsp_address},
                headers=admin,
            ) or {}
            if not cred.get("credentialId"):
                result.fail_step("issue-credential", "no credential id returned", body=cred)
                return result
            result.pass_step(
                "issue-credential",
                "OrganizationCredential issued",
                credential_id=cred.get("credentialId"),
            )
        except Exception as exc:
            result.fail_step("issue-credential", str(exc))
            return result

        # 10. Promote to a DSP participant (gate now satisfied)
        try:
            participant = self.http.post(
                f"{ir}/admin/owners/{urllib.parse.quote(alias)}/promote",
                {"dsp_address": dsp_address, "roles": ["consumer"]},
                headers=admin,
            ) or {}
            if participant.get("did") != did or not participant.get("active"):
                result.fail_step("promote", "participant not registered/active", body=participant)
                return result
            result.pass_step("promote", "organisation registered as an active participant")
        except Exception as exc:
            result.fail_step("promote", str(exc))
            return result

        # 11. Readiness — the participant is authorised for its scope and its
        #     did:web resolves publicly. A promoted org negotiates and pulls
        #     exactly as any participant (covered end to end by `smoke`).
        try:
            encoded_did = urllib.parse.quote(did, safe="")
            check = self.http.get(
                f"{ir}/admin/participants/check?did={encoded_did}&scope=dataspaces.query",
                headers=admin,
            ) or {}
            if not check.get("allowed"):
                result.fail_step(
                    "readiness", "participant not authorised for dataspaces.query", body=check
                )
                return result
            did_doc = self.http.get(f"{ir}/dids/{encoded_did}/did.json") or {}
            if not did_doc.get("id"):
                result.fail_step("readiness", "org did:web did not resolve", body=did_doc)
                return result
            result.pass_step(
                "readiness",
                "participant authorised and did:web resolves — transaction-ready",
                did=did,
            )
        except Exception as exc:
            result.fail_step("readiness", str(exc))
            return result

        # 12. Suspend — StatusList bit + participant deactivation in one step
        try:
            suspended = self.http.patch(
                f"{ir}/admin/owners/{urllib.parse.quote(alias)}",
                {"status": "suspended"},
                headers=admin,
            ) or {}
            if suspended.get("status") != "suspended":
                result.fail_step("suspend", "owner not suspended", body=suspended)
                return result
            creds = self.http.get(
                f"{ir}/admin/credentials?subject_did={urllib.parse.quote(did, safe='')}",
                headers=admin,
            ) or []
            org_creds = [c for c in creds if c.get("credential_type") == "OrganizationCredential"]
            if any(c.get("status") == "active" for c in org_creds):
                result.fail_step(
                    "suspend",
                    "OrganizationCredential still active after suspend",
                    creds=org_creds,
                )
                return result
            check = self.http.get(
                f"{ir}/admin/participants/check?did={urllib.parse.quote(did, safe='')}"
                "&scope=dataspaces.query",
                headers=admin,
            ) or {}
            if check.get("allowed"):
                result.fail_step("suspend", "participant still authorised after suspend")
                return result
            result.pass_step(
                "suspend",
                "suspend revoked the credential and deactivated the participant",
            )
        except Exception as exc:
            result.fail_step("suspend", str(exc))
            return result

        result.pass_step(
            "org-onboarding complete",
            "lifecycle, gates and readiness verified (DSP pull covered by `smoke`)",
        )
        return result
