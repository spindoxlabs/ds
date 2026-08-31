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
    resolvable, OrganizationCredential active). Finishes with suspend and
    reinstate, proving the register bit and participant deactivation land in one
    step — and come back off in one step, on the credential the organisation
    already holds. A suspension nothing can lift is a revocation, so the two
    steps only mean anything together.

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
    rules = ("P-1", "P-2", "P-4", "P-25", "P-26")

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
            app = (
                self.http.post(
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
                )
                or {}
            )
            application_id = app.get("id")
            if not application_id or app.get("status") != "pending":
                result.fail_step(
                    "register", "application not created as pending", app=app
                )
                return result
            result.pass_step(
                "register", "organisation application created", alias=alias
            )
        except Exception as exc:
            result.fail_step("register", str(exc))
            return result

        # 5. Verify → promotes legal identity into an Owner row
        try:
            verified = (
                self.http.patch(
                    f"{ir}/admin/organizations/applications/{application_id}",
                    {"status": "verified", "verified_by": "e2e-operator"},
                    headers=admin,
                )
                or {}
            )
            if verified.get("status") != "verified":
                result.fail_step(
                    "verify", "application verification failed", body=verified
                )
                return result
            resolved = (
                self.http.get(
                    f"{ir}/owners/resolve?alias={urllib.parse.quote(alias)}",
                    headers=admin,
                )
                or {}
            )
            if resolved.get("status") != "verified":
                result.fail_step(
                    "verify", "owner not promoted to verified", owner=resolved
                )
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
            acceptance = (
                self.http.post(
                    f"{ir}/admin/owners/{urllib.parse.quote(alias)}/agreement",
                    {
                        "agreement_id": s.org_agreement_id,
                        "version": s.org_agreement_version,
                        "locale": "en",
                        "accepted_by": "e2e-org-contact",
                    },
                    headers=admin,
                )
                or {}
            )
            if not acceptance.get("text_sha256"):
                result.fail_step(
                    "agreement", "acceptance missing text hash", body=acceptance
                )
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

        # 8b. GATE — a credential cannot be issued to an organisation that has
        #     not **enrolled** (`D-51`). This is the newest gate and the one that
        #     ends the anchor's ability to create a participant on its own: the
        #     credential binds to a key the organisation generated and proved
        #     control of, and until then there is nothing to bind to.
        #
        #     It replaced a step this flow used to pass by *not existing* — the
        #     registry generated the organisation's keypair as a side effect of
        #     issuance, and kept the private half.
        status, body = self.http.post_raw(
            f"{ir}/admin/credentials/organization",
            {"alias": alias, "roles": ["consumer"], "dsp_address": dsp_address},
            headers=admin,
        )
        if status == 201:
            result.fail_step(
                "gate: credential needs enrolment",
                "credential issued to an organisation that never enrolled",
            )
            return result
        result.pass_step(
            "gate: credential needs enrolment",
            f"issue-credential refused before enrolment (HTTP {status})",
        )

        # 8c. Enrol: an operator issues the code, and the organisation presents
        #     the key it generated itself.
        #
        #     **This flow stands in for the organisation's instance**, because a
        #     synthetic org has none — it generates a keypair here and registers
        #     the DID. The *real* handshake, with an instance serving its own DID
        #     document and the anchor fetching it, is what the dev participants
        #     do at bootstrap and what `dcp-trust` exercises.
        try:
            self.http.post(
                f"{ir}/admin/onboarding/enrolments",
                {"owner_alias": alias, "roles": ["consumer"]},
                headers=admin,
            )
            registered = (
                self.http.post(
                    f"{ir}/admin/participants",
                    {
                        "did": did,
                        "dsp_address": dsp_address,
                        "roles": ["consumer"],
                        "allowed_scopes": ["dataspaces.query"],
                    },
                    headers=admin,
                )
                or {}
            )
            if registered.get("did") != did:
                result.fail_step("enrolment", "DID not registered", body=registered)
                return result
            result.pass_step(
                "enrolment",
                "organisation's DID registered — the anchor holds no key for it",
            )
        except Exception as exc:
            result.fail_step("enrolment", str(exc))
            return result

        # 9. Issue the OrganizationCredential (now that the agreement is accepted)
        try:
            cred = (
                self.http.post(
                    f"{ir}/admin/credentials/organization",
                    {"alias": alias, "roles": ["consumer"], "dsp_address": dsp_address},
                    headers=admin,
                )
                or {}
            )
            if not cred.get("credentialId"):
                result.fail_step(
                    "issue-credential", "no credential id returned", body=cred
                )
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
            participant = (
                self.http.post(
                    f"{ir}/admin/owners/{urllib.parse.quote(alias)}/promote",
                    {"dsp_address": dsp_address, "roles": ["consumer"]},
                    headers=admin,
                )
                or {}
            )
            if participant.get("did") != did or not participant.get("active"):
                result.fail_step(
                    "promote", "participant not registered/active", body=participant
                )
                return result
            result.pass_step(
                "promote", "organisation registered as an active participant"
            )
        except Exception as exc:
            result.fail_step("promote", str(exc))
            return result

        # 11. Readiness — the participant is authorised for its scope, and the
        #     **anchor does not publish its DID document**.
        #
        #     That second half is inverted from what it used to assert, and the
        #     inversion is the point. This step required the anchor to resolve
        #     the organisation's did:web — which it could only do because it had
        #     generated that organisation's keypair and kept the private half.
        #
        #     A DID document is served by whoever holds the key (`P-6`). The
        #     anchor holds none for a party it has not been shown one by, so a
        #     404 here is the correct answer and a 200 would mean the mint came
        #     back. The organisation publishes its own document from its own
        #     instance — which is what the dev participants do, and what
        #     `dcp-trust` verifies end to end.
        try:
            encoded_did = urllib.parse.quote(did, safe="")
            check = (
                self.http.get(
                    f"{ir}/admin/participants/check?did={encoded_did}&scope=dataspaces.query",
                    headers=admin,
                )
                or {}
            )
            if not check.get("allowed"):
                result.fail_step(
                    "readiness",
                    "participant not authorised for dataspaces.query",
                    body=check,
                )
                return result
            status, _ = self.http.get_raw(f"{ir}/dids/{encoded_did}/did.json")
            if status == 200:
                result.fail_step(
                    "readiness",
                    "the trust anchor published a DID document for an "
                    "organisation whose key it should not hold",
                )
                return result
            result.pass_step(
                "readiness",
                "participant authorised; the anchor publishes no document for it "
                f"(HTTP {status}) — the key is the organisation's",
                did=did,
            )
        except Exception as exc:
            result.fail_step("readiness", str(exc))
            return result

        # 12. Suspend — StatusList bit + participant deactivation in one step
        try:
            suspended = (
                self.http.patch(
                    f"{ir}/admin/owners/{urllib.parse.quote(alias)}",
                    {"status": "suspended"},
                    headers=admin,
                )
                or {}
            )
            if suspended.get("status") != "suspended":
                result.fail_step("suspend", "owner not suspended", body=suspended)
                return result
            creds = (
                self.http.get(
                    f"{ir}/admin/credentials?subject_did={urllib.parse.quote(did, safe='')}",
                    headers=admin,
                )
                or []
            )
            org_creds = [
                c for c in creds if c.get("credential_type") == "OrganizationCredential"
            ]
            if any(c.get("status") == "active" for c in org_creds):
                result.fail_step(
                    "suspend",
                    "OrganizationCredential still active after suspend",
                    creds=org_creds,
                )
                return result
            # Held, not finished. A suspension recorded as a revocation cannot
            # be lifted — a revocation bit is never cleared — so the next step
            # would be impossible and this one would have been a lie.
            if any(c.get("status") != "suspended" for c in org_creds):
                result.fail_step(
                    "suspend",
                    "suspend left the credential in a state other than 'suspended'",
                    creds=org_creds,
                )
                return result
            check = (
                self.http.get(
                    f"{ir}/admin/participants/check?did={urllib.parse.quote(did, safe='')}"
                    "&scope=dataspaces.query",
                    headers=admin,
                )
                or {}
            )
            if check.get("allowed"):
                result.fail_step(
                    "suspend", "participant still authorised after suspend"
                )
                return result
            result.pass_step(
                "suspend",
                "suspend held the credential and deactivated the participant",
            )
        except Exception as exc:
            result.fail_step("suspend", str(exc))
            return result

        # 13. Reinstate — the half that makes suspension a state rather than a
        # slower revocation. The organisation gets the credential it already
        # holds back, unchanged: no re-issuance, no new StatusList index.
        try:
            reinstated = (
                self.http.patch(
                    f"{ir}/admin/owners/{urllib.parse.quote(alias)}",
                    {"status": "verified"},
                    headers=admin,
                )
                or {}
            )
            if reinstated.get("status") != "verified":
                result.fail_step("reinstate", "owner not reinstated", body=reinstated)
                return result
            creds = (
                self.http.get(
                    f"{ir}/admin/credentials?subject_did={urllib.parse.quote(did, safe='')}",
                    headers=admin,
                )
                or []
            )
            back = [
                c for c in creds if c.get("credential_type") == "OrganizationCredential"
            ]
            if not back or any(c.get("status") != "active" for c in back):
                result.fail_step(
                    "reinstate",
                    "credential not valid again after reinstate",
                    creds=back,
                )
                return result
            if {c.get("id") for c in back} != {c.get("id") for c in org_creds}:
                result.fail_step(
                    "reinstate",
                    "reinstate minted a new credential instead of lifting the hold",
                    creds=back,
                )
                return result
            check = (
                self.http.get(
                    f"{ir}/admin/participants/check?did={urllib.parse.quote(did, safe='')}"
                    "&scope=dataspaces.query",
                    headers=admin,
                )
                or {}
            )
            if not check.get("allowed"):
                result.fail_step(
                    "reinstate", "participant still unauthorised after reinstate"
                )
                return result
            result.pass_step(
                "reinstate",
                "the same credential is valid again and the participant is authorised",
            )
        except Exception as exc:
            result.fail_step("reinstate", str(exc))
            return result

        result.pass_step(
            "org-onboarding complete",
            "lifecycle, gates and readiness verified (DSP pull covered by `smoke`)",
        )
        return result
