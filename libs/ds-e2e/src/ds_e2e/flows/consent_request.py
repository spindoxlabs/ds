"""The interactive consent lifecycle — an ask is raised, a subject decides.

The `smoke` flow covers the *standing* path: a subject publishes an ongoing
sharing decision against an offer, and consumers draw on it. This flow covers
the other half of the consent model, which had no end-to-end coverage at all:
an ask names a dataset and a set of subjects, each subject sees a pending
request in their own inbox, and each decides.

The ask is seeded through `POST /consent/request`, the provider-local route an
operator or the portal uses. In the DSP path the same rows are written by
`ConsentPendingGuard` from a parked negotiation, with the requester's identity
taken from EDC's DCP-verified `counterPartyId` — the lifecycle from there on is
identical, so this flow asserts it without needing an EDC running.

What it proves, in order:

- an ask lands *pending* — never pre-approved;
- the pending request appears to the subject it names, and to nobody else;
- a rejection is final: the consent check stays closed and re-deciding a
  settled request is refused;
- an approval opens the check for the granted purpose, and only that purpose;
- a revocation closes it again, and the record keeps the decision history
  rather than disappearing;
- the whole sequence leaves a provenance trail.

Needs no EDC: connector, identity-registry and Keycloak are enough.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class ConsentRequestFlow(BaseFlow):
    name = "consent-request"
    description = (
        "Interactive consent: an ask lands pending, the subject sees it, "
        "rejects/approves/revokes, with enforcement asserted at each transition"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        try:
            self.http.get(f"{s.connector_url}/health")
            result.pass_step("health", "connector reachable")
        except Exception as exc:
            result.fail_step("health", str(exc))
            return result

        try:
            svc_headers = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        try:
            subject_vc = self._resolve_user_vc(s.data_subject_email, svc_headers)
        except Exception as exc:
            result.fail_step("load credentials", str(exc))
            return result

        subject_headers = {"X-Subject-Id": s.data_subject_id, "X-User-VC": subject_vc}

        # ── 1. An ask is raised on the provider ──────────────────────────────
        request_body = {
            "consumer_id": s.consumer_did,
            "dataset_id": s.asset_id,
            "subject_ids": [s.data_subject_id],
            "purpose": [s.consented_purpose],
            "offer_id": s.sharing_offer_id,
            "message": "e2e uc4 — interactive consent lifecycle",
        }
        # Raised against the *provider* connector, as a service. That is where
        # `/internal/consent/check` reads from, so it is the only place a row can
        # land and still gate access.
        #
        # It is no longer raised with the consumer's own credential. A consumer
        # asking for data now simply negotiates: `ConsentPendingGuard` parks the
        # negotiation and records the ask from EDC's DCP-verified
        # `counterPartyId`. `POST /consent/request` is what remains for the
        # provider-local case — an operator or the portal seeding an ask — and it
        # authenticates as a service accordingly. The lifecycle asserted below is
        # the same one the guard produces; this drives it without needing an EDC.
        status, payload = self.http.raw(
            "POST",
            f"{s.connector_url}/consent/request",
            body=request_body,
            headers=svc_headers,
        )
        if status != 201 or not isinstance(payload, dict):
            result.fail_step(
                "provider seeds a consent request",
                "consent request was not created",
                status_code=status,
                response=payload,
                target=f"{s.connector_url}/consent/request",
            )
            return result
        request_ids = payload.get("request_ids") or []
        if not request_ids or payload.get("status") != "pending":
            result.fail_step(
                "provider seeds a consent request",
                "request did not land in pending state",
                response=payload,
            )
            return result
        consent_id = str(request_ids[0])
        result.pass_step(
            "provider seeds a consent request",
            "the ask landed pending, not pre-approved",
            consent_id=consent_id,
        )

        # ── 2. Pending, and closed until decided ─────────────────────────────
        #     A request is not a grant. Until the subject acts, the check that
        #     gates data access must stay shut.
        check = self._consent_check(svc_headers, purpose=s.consented_purpose)
        if check.get("consent_active"):
            result.fail_step(
                "pending is not granted",
                "an undecided request already authorised access",
                check=check,
            )
            return result
        result.pass_step(
            "pending is not granted",
            "an undecided request does not authorise access",
            reason=check.get("reason"),
        )

        # ── 3. The subject sees it, and only its own ─────────────────────────
        inbox = self.http.get(
            f"{s.connector_url}/consent/my?status=pending", headers=subject_headers
        ) or []
        mine = [c for c in inbox if c.get("id") == consent_id]
        if not mine:
            result.fail_step(
                "subject inbox",
                "the pending request is not visible to the subject it names",
                consent_id=consent_id,
                inbox_ids=[c.get("id") for c in inbox],
            )
            return result
        foreign = [c for c in inbox if c.get("subject_id") != s.data_subject_id]
        if foreign:
            result.fail_step(
                "subject inbox",
                "the inbox contains requests belonging to other subjects",
                foreign=[c.get("id") for c in foreign],
            )
            return result
        record = mine[0]
        if record.get("purpose") != [s.consented_purpose]:
            result.fail_step(
                "subject inbox",
                "the request does not carry the purpose it was raised for",
                purpose=record.get("purpose"),
            )
            return result
        result.pass_step(
            "subject inbox",
            "the subject sees its own pending request, stamped with the purpose",
            consent_id=consent_id,
            purpose=record.get("purpose"),
        )

        # ── 4. Rejection is final ────────────────────────────────────────────
        rejected = self.http.post(
            f"{s.connector_url}/consent/my/{consent_id}/reject", {}, headers=subject_headers
        ) or {}
        if rejected.get("status") != "rejected":
            result.fail_step("subject rejects", "reject did not settle the request", response=rejected)
            return result

        check = self._consent_check(svc_headers, purpose=s.consented_purpose)
        if check.get("consent_active"):
            result.fail_step(
                "subject rejects",
                "a rejected request still authorised access",
                check=check,
            )
            return result

        # A settled decision must not be re-openable by replaying the approve
        # call — otherwise "reject" is advisory.
        replay_status, _ = self.http.raw(
            "POST",
            f"{s.connector_url}/consent/my/{consent_id}/approve",
            body={},
            headers=subject_headers,
        )
        if replay_status < 400:
            result.fail_step(
                "subject rejects",
                "a rejected request was re-approved by replaying the decision",
                status_code=replay_status,
            )
            return result
        result.pass_step(
            "subject rejects",
            "rejection closes the check and cannot be replayed into an approval",
            replay_refused_with=replay_status,
        )

        # ── 5. A second request, this time approved ──────────────────────────
        status, payload = self.http.raw(
            "POST",
            f"{s.connector_url}/consent/request",
            body={**request_body, "message": "e2e uc4 — approval path"},
            headers=svc_headers,
        )
        if status != 201 or not isinstance(payload, dict) or not payload.get("request_ids"):
            result.fail_step(
                "second request",
                "could not raise a second consent request after rejection",
                status_code=status,
                response=payload,
            )
            return result
        approve_id = str(payload["request_ids"][0])

        approved = self.http.post(
            f"{s.connector_url}/consent/my/{approve_id}/approve", {}, headers=subject_headers
        ) or {}
        if approved.get("status") != "granted":
            result.fail_step("subject approves", "approve did not grant", response=approved)
            return result

        check = self._consent_check(svc_headers, purpose=s.consented_purpose)
        if not check.get("consent_active"):
            result.fail_step(
                "subject approves",
                "an approved request did not authorise access",
                check=check,
            )
            return result
        result.pass_step(
            "subject approves",
            "approval opens the consent check for the granted purpose",
            consent_id=approve_id,
        )

        # ── 6. The grant is bounded by its purpose ───────────────────────────
        #     Approving one purpose must not authorise another. This is the
        #     assertion that distinguishes a purpose-bound consent record from a
        #     boolean flag.
        other = self._consent_check(svc_headers, purpose=s.unconsented_purpose)
        if other.get("consent_active"):
            result.fail_step(
                "grant is purpose-bound",
                "a grant for one purpose authorised another",
                granted=s.consented_purpose,
                probed=s.unconsented_purpose,
            )
            return result
        result.pass_step(
            "grant is purpose-bound",
            "the grant does not extend to a purpose the subject did not agree to",
            probed=s.unconsented_purpose,
        )

        # ── 7. Revocation closes it, and the record survives ─────────────────
        revoked = self.http.post(
            f"{s.connector_url}/consent/my/{approve_id}/revoke", {}, headers=subject_headers
        ) or {}
        if revoked.get("status") != "revoked":
            result.fail_step("subject revokes", "revoke did not settle", response=revoked)
            return result

        check = self._consent_check(svc_headers, purpose=s.consented_purpose)
        if check.get("consent_active"):
            result.fail_step(
                "subject revokes",
                "a revoked consent still authorised access",
                check=check,
            )
            return result

        # Withdrawal is not erasure: the decision history is the evidence that
        # the processing was once lawful, and that it stopped.
        after = self.http.get(
            f"{s.connector_url}/consent/my/{approve_id}", headers=subject_headers
        ) or {}
        if after.get("status") != "revoked" or not after.get("revoked_at"):
            result.fail_step(
                "subject revokes",
                "the revoked record did not retain its decision history",
                record=after,
            )
            return result
        result.pass_step(
            "subject revokes",
            "revocation closes the check and the record retains when it was decided and withdrawn",
            decided_at=after.get("decided_at"),
            revoked_at=after.get("revoked_at"),
        )

        # ── 8. The sequence is on the record ─────────────────────────────────
        self._check_provenance(result, svc_headers)
        return result

    # ── helpers ──────────────────────────────────────────────────────────────

    def _consent_check(self, headers: dict[str, str], *, purpose: str) -> dict[str, Any]:
        s = self.settings
        query = urllib.parse.urlencode(
            {
                "dataset_id": s.asset_id,
                "consumer_id": s.consumer_did,
                "subject_id": s.data_subject_id,
                "purpose": purpose,
            }
        )
        return self.http.get(
            f"{s.connector_url}/internal/consent/check?{query}", headers=headers
        ) or {}

    def _check_provenance(self, result: FlowResult, headers: dict[str, str]) -> None:
        """The decisions must be reconstructable from the provenance store.

        A consent trail that lives only in the connector's own table proves
        nothing to a third party — the point of emitting these events is that
        the record of who decided what, and when, is independent of the service
        that enforced it.
        """
        s = self.settings
        expected = {"ConsentGranted", "ConsentRevoked"}
        try:
            events = self.http.get(
                f"{s.provenance_url}/prov/events?limit=200", headers=headers
            ) or {}
        except Exception as exc:
            result.fail_step("consent provenance", f"provenance unreachable: {exc}")
            return
        observed = {
            str(item.get("@type", "")).removeprefix("ds:")
            for item in (events.get("@graph") or [])
            if isinstance(item, dict)
        }
        missing = sorted(expected - observed)
        if missing:
            result.fail_step(
                "consent provenance",
                "the consent decisions left no provenance record",
                missing=missing,
                observed=sorted(observed),
            )
            return
        result.pass_step(
            "consent provenance",
            "grant and revocation are recorded in the provenance store",
            events=sorted(expected),
        )

    def _resolve_user_vc(self, email: str, headers: dict[str, str]) -> str:
        s = self.settings
        encoded = urllib.parse.quote(email, safe="")
        resp = self.http.get(
            f"{s.identity_registry_url}/users/resolve?email={encoded}", headers=headers
        ) or {}
        vc_jws = resp.get("vc_jws") or ""
        if not vc_jws:
            raise RuntimeError(f"No VC found for user {email}")
        return vc_jws
