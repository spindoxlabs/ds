"""Authorisation perimeter — can a valid caller reach someone else's data?

The `api-contract` flow proves an *invalid* caller is refused. This one asks the
harder question, and the one that produces most real breaches: a caller who is
fully authenticated, holds a genuine credential, and is entitled to use the API —
can they reach a record that is not theirs?

Three failure modes, each probed with real credentials issued by the
identity-registry:

- **Horizontal escalation.** One data subject reading or acting on another
  subject's consent. The connector derives the acting subject from headers the
  client controls, so every one of those paths needs an explicit assertion that
  the header cannot be pointed at a stranger.
- **Role confusion.** A ConsumerUser credential used on a DataSubject-only
  endpoint, and the reverse. Both credentials are valid; only the role
  distinguishes them, and the role is what decides who may consent on whose
  behalf.
- **Enumeration.** A record that exists but belongs to someone else must be
  indistinguishable from one that does not exist — otherwise the 403/404
  difference is itself a directory of other people's consents.

Needs no EDC: connector and identity-registry are enough.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class AuthzPerimeterFlow(BaseFlow):
    name = "authz-perimeter"
    description = (
        "Cross-subject isolation, role confusion and enumeration resistance on "
        "the credential-authenticated API"
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

        # Two genuine credentials with different roles and different subjects.
        try:
            subject_vc = self._resolve_user_vc(s.data_subject_email, svc_headers)
            consumer_vc = self._resolve_user_vc(s.consumer_email, svc_headers)
        except Exception as exc:
            result.fail_step("load credentials", str(exc))
            return result

        subject_headers = {"X-Subject-Id": s.data_subject_id, "X-User-VC": subject_vc}
        consumer_headers = {"X-Subject-Id": s.consumer_subject_id, "X-User-VC": consumer_vc}

        # The credentials must actually work, or every negative below would pass
        # for the wrong reason.
        status, _ = self.http.raw(
            "GET", f"{s.connector_url}/consent/my", headers=subject_headers
        )
        if status != 200:
            result.fail_step(
                "credential baseline",
                "the data subject's own credential was refused on its own endpoint — "
                "the negative assertions below would be vacuous",
                status_code=status,
            )
            return result
        result.pass_step(
            "credential baseline",
            "both credentials resolve and the subject can read its own consents",
        )

        self._check_header_substitution(result, subject_headers, consumer_headers)
        self._check_query_parameter_scoping(result, subject_headers)
        self._check_role_confusion(result, subject_headers, consumer_headers)
        self._check_enumeration(result, subject_headers)

        return result

    # ── horizontal escalation ────────────────────────────────────────────────

    def _check_header_substitution(
        self,
        result: FlowResult,
        subject_headers: dict[str, str],
        consumer_headers: dict[str, str],
    ) -> None:
        """Pointing X-Subject-Id at a stranger must not act as that stranger.

        The acting subject comes from a request header. The credential is what
        binds that header to a real person — so the credential and the header
        must be checked *against each other*, not merely both present. A caller
        who swaps the header while keeping their own valid credential is the
        canonical horizontal-escalation attempt.
        """
        s = self.settings
        victim = s.consumer_subject_id
        attacker_vc = subject_headers["X-User-VC"]

        mismatched = {"X-Subject-Id": victim, "X-User-VC": attacker_vc}
        probes = [
            ("GET", "/consent/my", None),
            ("GET", "/consent/my/shares", None),
            ("POST", "/consent/my/shares", {"offer_id": s.sharing_offer_id, "enabled": True}),
        ]

        accepted: list[str] = []
        for method, path, body in probes:
            status, _ = self.http.raw(
                method, f"{s.connector_url}{path}", body=body, headers=mismatched
            )
            if status < 400:
                accepted.append(f"{method} {path} → {status}")

        # And the reverse direction, so the assertion is not an artefact of one
        # credential happening to be weaker than the other.
        reversed_headers = {
            "X-Subject-Id": s.data_subject_id,
            "X-User-VC": consumer_headers["X-User-VC"],
        }
        status, _ = self.http.raw(
            "GET", f"{s.connector_url}/consent/my", headers=reversed_headers
        )
        if status < 400:
            accepted.append(f"reverse GET /consent/my → {status}")

        if accepted:
            result.fail_step(
                "header substitution",
                "a valid credential acted on behalf of a different subject",
                accepted=accepted,
            )
            return
        result.pass_step(
            "header substitution",
            "a credential cannot act for a subject other than the one it names",
            probes=len(probes) + 1,
        )

    def _check_query_parameter_scoping(
        self, result: FlowResult, subject_headers: dict[str, str]
    ) -> None:
        """A subject_id in the query string must not widen the caller's reach.

        `/consent/status` takes the subject as a query parameter while
        authenticating the caller from headers. Without an explicit equality
        check, any authenticated holder could enumerate any subject's consent
        decisions one query at a time.
        """
        s = self.settings
        params = urllib.parse.urlencode(
            {
                "consumer_id": s.consumer_did,
                "dataset_id": s.asset_id,
                "subject_id": s.consumer_subject_id,  # not the authenticated caller
            }
        )
        status, body = self.http.raw(
            "GET", f"{s.connector_url}/consent/status?{params}", headers=subject_headers
        )
        if status < 400:
            result.fail_step(
                "query-parameter scoping",
                "consent status for another subject was disclosed",
                status_code=status,
                body=body,
            )
            return

        # The caller's own subject must still work, so the check is a scope
        # restriction and not a blanket denial.
        own_params = urllib.parse.urlencode(
            {
                "consumer_id": s.consumer_did,
                "dataset_id": s.asset_id,
                "subject_id": s.data_subject_id,
            }
        )
        own_status, _ = self.http.raw(
            "GET", f"{s.connector_url}/consent/status?{own_params}", headers=subject_headers
        )
        if own_status != 200:
            result.fail_step(
                "query-parameter scoping",
                "the caller could not read its own consent status either — the "
                "restriction is a blanket denial, not a perimeter",
                status_code=own_status,
            )
            return
        result.pass_step(
            "query-parameter scoping",
            "a subject_id parameter naming someone else is refused; the caller's own is served",
            refused_with=status,
        )

    # ── role confusion ───────────────────────────────────────────────────────

    def _check_role_confusion(
        self,
        result: FlowResult,
        subject_headers: dict[str, str],
        consumer_headers: dict[str, str],
    ) -> None:
        """The role in the credential decides which half of the API is reachable.

        A ConsumerUser asks for data; a DataSubject decides whether it is given.
        Collapsing those two would let the party that benefits from a consent be
        the party that records it.
        """
        s = self.settings
        accepted: list[str] = []

        # ConsumerUser must not exercise the subject's decision endpoints.
        subject_only: list[tuple[str, str, dict[str, Any] | None]] = [
            (
                "POST",
                f"{s.connector_url}/consent/my/shares",
                {"offer_id": s.sharing_offer_id, "enabled": True},
            ),
            ("GET", f"{s.connector_url}/consent/my/shares", None),
        ]
        for method, url, body in subject_only:
            status, _ = self.http.raw(method, url, body=body, headers=consumer_headers)
            if status < 400:
                accepted.append(f"ConsumerUser on {method} {url.rsplit('/', 2)[-2:]} → {status}")

        # DataSubject must not drive the consumer's acquisition endpoints.
        consumer_only: list[tuple[str, str, dict[str, Any] | None]] = [
            (
                "POST",
                f"{s.consumer_connector_url}/consumer/negotiate",
                {
                    "counter_party_address": s.counter_party_address,
                    "offer_id": "e2e-role-probe",
                    "asset_id": s.asset_id,
                    "assigner": s.provider_did,
                },
            ),
            ("GET", f"{s.consumer_connector_url}/consumer/requests", None),
        ]
        for method, url, body in consumer_only:
            status, _ = self.http.raw(method, url, body=body, headers=subject_headers)
            if status < 400:
                accepted.append(f"DataSubject on {method} {url.rsplit('/', 2)[-2:]} → {status}")

        # Operator-only provisioning must not be reachable with a user credential
        # at all — it writes a consent row on the subject's behalf.
        status, _ = self.http.raw(
            "POST",
            f"{s.connector_url}/consent/admin/shares",
            body={"subject_id": s.data_subject_id, "offer_id": s.sharing_offer_id, "enabled": True},
            headers=subject_headers,
        )
        if status < 400:
            accepted.append(f"DataSubject on POST /consent/admin/shares → {status}")

        if accepted:
            result.fail_step(
                "role confusion",
                "a credential reached an endpoint reserved for a different role",
                accepted=accepted,
            )
            return
        result.pass_step(
            "role confusion",
            "subject-only, consumer-only and operator-only endpoints each refuse the other roles",
            probes=len(subject_only) + len(consumer_only) + 1,
        )

    # ── enumeration ──────────────────────────────────────────────────────────

    def _check_enumeration(self, result: FlowResult, subject_headers: dict[str, str]) -> None:
        """Someone else's record must look exactly like no record.

        If fetching a consent that exists but belongs to another subject answers
        403 while a fabricated id answers 404, the pair of responses is an oracle:
        it confirms which identifiers are real. Both must answer the same way.
        """
        s = self.settings
        fabricated = "00000000-0000-4000-8000-000000000000"
        status_fabricated, _ = self.http.raw(
            "GET", f"{s.connector_url}/consent/my/{fabricated}", headers=subject_headers
        )

        # A record that genuinely belongs to someone else. Provisioned through
        # the operator path so the flow does not depend on prior state; if the
        # provisioning is unavailable the probe degrades to the fabricated-id
        # assertion rather than silently passing.
        try:
            svc_headers = self.http.bearer_headers()
            rows = self.http.post(
                f"{s.connector_url}/consent/admin/shares",
                {
                    "subject_id": s.consumer_subject_id,
                    "offer_id": s.sharing_offer_id,
                    "enabled": True,
                    "legal_basis": {"source": "e2e", "submission_ref": "authz-perimeter"},
                },
                headers=svc_headers,
            ) or []
            rows = rows if isinstance(rows, list) else [rows]
            foreign_id = next((r.get("id") for r in rows if r.get("id")), None)
        except Exception as exc:
            log.debug("Could not provision a foreign consent row: %s", exc)
            foreign_id = None

        if status_fabricated < 400:
            result.fail_step(
                "enumeration resistance",
                "a fabricated consent id was served",
                status_code=status_fabricated,
            )
            return

        if foreign_id is None:
            result.pass_step(
                "enumeration resistance",
                "a fabricated consent id is refused (foreign-record comparison skipped — "
                "operator provisioning unavailable)",
                fabricated=status_fabricated,
            )
            return

        status_foreign, _ = self.http.raw(
            "GET",
            f"{s.connector_url}/consent/my/{urllib.parse.quote(str(foreign_id), safe='')}",
            headers=subject_headers,
        )
        if status_foreign < 400:
            result.fail_step(
                "enumeration resistance",
                "another subject's consent record was disclosed",
                consent_id=foreign_id,
                status_code=status_foreign,
            )
            return
        if status_foreign != status_fabricated:
            result.fail_step(
                "enumeration resistance",
                "an existing foreign record is distinguishable from a fabricated one",
                foreign=status_foreign,
                fabricated=status_fabricated,
            )
            return
        result.pass_step(
            "enumeration resistance",
            "a foreign consent id is indistinguishable from a nonexistent one",
            status_code=status_foreign,
        )

    # ── helpers ──────────────────────────────────────────────────────────────

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
