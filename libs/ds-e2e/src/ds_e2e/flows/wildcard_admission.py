"""D-14 — who an offer-scoped grant admits, live.

A person who consents to a *sharing offer* rather than to a named counterparty
gets a wildcard row: `consumer_id = "*"`. D-14 says what that row means — "the
wildcard admits any party **inside the circle** for that controller and purpose.
It never admits a new controller and never a new purpose."

The purpose half has end-to-end coverage; the controller half has none, and it
is the half that is wrong. Both readers hand the requesting consumer straight to
`get_granted_subject_ids`, which matches `{consumer_id, "*"}` — so the wildcard
row answers for *whoever* asks. `circle.py` knows a controller from a processor
and is consulted only when no consent covers the request, so the one case it
exists for never reaches it.

**Why a flow and not only unit tests.** The unit tests stub
`circle._agreement_capacity`, so they assert the rule while assuming the input.
Here nothing is stubbed: capacity is read from what each organisation actually
signed, through `GET /agreements/current`, and the flow refuses to run if the
fixtures do not declare what it expects.

The two parties:

- `example-org` — `did:web:rec.dataspaces.localhost`, the offer's **controller**,
  admitted. That this is also the provider's own DID is not a coincidence to work
  around: the community is the controller of what its members consented to, and
  reading its own members' rows is what onboarding's POD-list export does.
- `outsider-org` — `did:web:outsider.dataspaces.localhost`, which accepted
  `independent-controller-participation` (`capacity: independent_controller`) and
  is **deliberately not a member of `example-org`**. The scenario says why: *"it
  fails both halves of the circle definition, which is the case that must produce
  a consent request."*

**Not `consumer_did`.** `did:web:third-party.dataspaces.localhost` accepts
`dataspace-participation`, whose capacity is `processor`, but it is not a member
of `example-org`. Whether a wildcard admits it therefore depends on the offer's
`admitted_by`, which is ANDed: an offer that also requires that membership leaves
it outside. It is the wrong party for this flow either way, because the refusal
here must come from *capacity*, the half `outsider-org` is built to fail.
`onboarding-seam` asserts the membership half on the audience read.

Needs `ds-e2e scenario apply` (`energy-chains`), which is what registers
`outsider-org`. `task e2e:fast` declares it as a dependency; run it first when
running this flow alone.

Needs no EDC. `should_ask` is the flag `ConsentPendingGuard` parks on, and it is
served by `/internal/consent/check`, so the parking decision is asserted without
an EDC running — the same technique `consent-request` uses.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import psycopg

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

RECIPIENT_ALIAS = "example-org"

# The independent controller, from `scenarios/energy-chains.yaml`.
OUTSIDER_ALIAS = "outsider-org"
OUTSIDER_DID = "did:web:outsider.dataspaces.localhost"
EXPECTED_CAPACITY = "independent_controller"


class WildcardAdmissionFlow(BaseFlow):
    name = "wildcard-admission"
    description = (
        "An offer-scoped grant admits the offer's controller and nobody else: "
        "a second consumer with no declared capacity is refused and asked"
    )
    rules = ("D-14", "D-15")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Held for `cleanup()`, which runs in a `finally` — including the paths
        # where `execute` returned early and the grant is still standing.
        self._subject: dict[str, str] | None = None
        self._wrote_rows = False

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        if not self._check_health(result):
            return result

        try:
            svc = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        try:
            self._subject = {
                "X-Subject-Id": s.data_subject_id,
                "X-User-VC": self._resolve_user_vc(s.data_subject_email, svc),
            }
        except Exception as exc:
            result.fail_step("load credentials", str(exc))
            return result
        subject = self._subject

        # ── 0. The fixture declares what this flow assumes ───────────────────
        #     Capacity is the input to the whole assertion. A scenario that was
        #     never applied, or one whose outsider signed the wrong agreement,
        #     would make step 3 pass or fail for a reason that has nothing to do
        #     with D-14 — so it is a precondition failure, never a silent skip.
        status, current = self.http.raw(
            "GET",
            f"{s.identity_registry_url}/agreements/current?"
            + urllib.parse.urlencode({"participant_did": OUTSIDER_DID}),
            headers=svc,
        )
        if status != 200 or not isinstance(current, dict):
            result.fail_step(
                "the independent controller is registered",
                f"no current agreement resolves for {OUTSIDER_ALIAS} — "
                "run `ds-e2e scenario apply`",
                status_code=status,
                participant=OUTSIDER_DID,
            )
            return result
        capacity = str(current.get("capacity"))
        if capacity != EXPECTED_CAPACITY:
            result.fail_step(
                "the independent controller is registered",
                f"{OUTSIDER_ALIAS} declares capacity {capacity!r}, and this flow "
                f"asserts the refusal of an {EXPECTED_CAPACITY!r}",
                participant=OUTSIDER_DID,
            )
            return result
        result.pass_step(
            "the independent controller is registered",
            "the second consumer's capacity is read from what it signed",
            capacity=capacity,
        )

        # ── 1. The member consents to the offer, not to a counterparty ───────
        #     Omitting `consumer_id` is what makes the row a wildcard. That
        #     default is deliberate (issue #33): keying the row on a resolved
        #     controller DID makes a withdrawal fail open under D-15 and forks
        #     the member's decision from the operator-recorded twin.
        self._wrote_rows = True
        try:
            rows = (
                self.http.post(
                    f"{s.connector_url}/consent/my/shares",
                    {"offer_id": s.sharing_offer_id, "enabled": True},
                    headers=subject,
                )
                or []
            )
        except Exception as exc:
            result.fail_step("member consents to the offer", str(exc))
            return result
        rows = rows if isinstance(rows, list) else [rows]
        consumers = {r.get("consumer_id") for r in rows}
        controllers = {r.get("recipient") for r in rows}
        if consumers != {"*"}:
            result.fail_step(
                "member consents to the offer",
                "the offer-scoped grant was not stored as a wildcard row",
                consumer_ids=sorted(str(c) for c in consumers),
            )
            return result
        if controllers != {RECIPIENT_ALIAS}:
            result.fail_step(
                "member consents to the offer",
                "the wildcard row is not stamped with the offer's controller",
                recipients=sorted(str(c) for c in controllers),
                expected=RECIPIENT_ALIAS,
            )
            return result
        result.pass_step(
            "member consents to the offer",
            "the grant is a wildcard row stamped with the offer's controller",
            recipient=RECIPIENT_ALIAS,
            purpose=s.consented_purpose,
        )

        # ── 2. The controller is admitted ────────────────────────────────────
        #     The party the person actually consented to. If this goes red the
        #     wildcard has stopped meaning anything and onboarding's POD-list
        #     export goes with it.
        check = self._check(svc, consumer_id=s.provider_did)
        if not check.get("consent_active"):
            result.fail_step(
                "the controller is admitted",
                "the offer's own controller was refused by the grant naming it",
                recipient_did=s.provider_did,
                reason=check.get("reason"),
            )
            return result
        result.pass_step(
            "the controller is admitted",
            "the party the offer names as controller reads the consented rows",
            recipient_did=s.provider_did,
        )

        # ── 3. The defect: a second consumer rides the same row ──────────────
        #     `third-party` is a verified owner with no agreement, so it has no
        #     declared capacity and the circle resolves it outside. Consent
        #     under Art. 4(11) is consent to a specific controller's processing;
        #     EDPB 05/2020 para 65 requires other controllers relying on that
        #     consent to be named. Nobody named this one.
        check = self._check(svc, consumer_id=OUTSIDER_DID)
        if check.get("consent_active"):
            result.fail_step(
                "a second consumer is refused",
                "an independent controller read the member's rows on a grant the "
                "member made to the offer's controller",
                consumer_did=OUTSIDER_DID,
                recipient=RECIPIENT_ALIAS,
            )
            return result
        result.pass_step(
            "a second consumer is refused",
            "a party outside the circle is not consented, whatever its agreement says",
            consumer_did=OUTSIDER_DID,
            reason=check.get("reason"),
        )

        # ── 4. …and the refusal is a question, not a dead end ────────────────
        #     `should_ask` is what `ConsentPendingGuard` parks on. A refusal
        #     that did not raise the question would simply lock the consumer
        #     out, which is not the remedy — being asked is.
        if not check.get("should_ask"):
            result.fail_step(
                "the refusal parks the negotiation",
                "the consumer was refused without the person being asked, so the "
                "negotiation would fail rather than park",
                consumer_did=OUTSIDER_DID,
            )
            return result
        result.pass_step(
            "the refusal parks the negotiation",
            "should_ask is set, so the guard parks and the person is asked",
            consumer_did=OUTSIDER_DID,
        )

        # ── 5. The audience read agrees with the per-subject check ───────────
        #     `/internal/consent/check` without a `subject_id` is the list the
        #     data plane filters rows on. It reads the same rows by a different
        #     path, so a fix applied to one and not the other shows up here.
        audience = self._check(svc, consumer_id=OUTSIDER_DID, subject_id=None)
        listed = audience.get("subject_ids") or []
        if s.data_subject_id in listed:
            result.fail_step(
                "the audience read agrees",
                "the per-subject check refused the consumer but the audience read "
                "still lists the subject, so the data plane would hand over rows",
                consumer_did=OUTSIDER_DID,
                subject_ids=listed,
            )
            return result
        result.pass_step(
            "the audience read agrees",
            "the row filter the data plane would apply excludes the subject",
            consumer_did=OUTSIDER_DID,
        )

        # ── 6. The remedy is open: a per-party grant admits them (D-15) ──────
        #     What the wildcard stops admitting, an answer to the question
        #     admits. Without this the fix would be indistinguishable from
        #     "third parties can never read", which is not what D-14 says.
        try:
            self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {
                    "offer_id": s.sharing_offer_id,
                    "consumer_id": OUTSIDER_DID,
                    "enabled": True,
                },
                headers=subject,
            )
        except Exception as exc:
            result.fail_step("a per-party grant admits them", str(exc))
            return result

        check = self._check(svc, consumer_id=OUTSIDER_DID)
        if not check.get("consent_active"):
            result.fail_step(
                "a per-party grant admits them",
                "the person named this consumer and it was still refused, so the "
                "narrowing has closed the door D-15 is supposed to open",
                consumer_did=OUTSIDER_DID,
                reason=check.get("reason"),
            )
            return result
        result.pass_step(
            "a per-party grant admits them",
            "a grant naming the consumer admits it, which is the remedy for step 3",
            consumer_did=OUTSIDER_DID,
        )

        return result

    # ── helpers ──────────────────────────────────────────────────────────────

    def _check(
        self,
        headers: dict[str, str],
        *,
        consumer_id: str,
        subject_id: str | None = "",
    ) -> dict[str, Any]:
        """`/internal/consent/check`, per-subject or as an audience read.

        ``subject_id=""`` means *this flow's subject*; ``None`` omits the
        parameter, which is the audience form the data plane uses.
        """
        s = self.settings
        params: dict[str, str] = {
            "dataset_id": s.asset_id,
            "consumer_id": consumer_id,
            "purpose": s.consented_purpose,
        }
        if subject_id is not None:
            params["subject_id"] = subject_id or s.data_subject_id
        return (
            self.http.get(
                f"{s.connector_url}/internal/consent/check?"
                + urllib.parse.urlencode(params),
                headers=headers,
            )
            or {}
        )

    def cleanup(self) -> None:
        """Delete this flow's own rows — never withdraw them.

        **Withdrawing is what broke `onboarding-seam`**, and the mechanism is
        worth stating because it is not obvious. `POST /consent/my/shares` with
        `enabled: false` writes a *withdrawal made by the subject*, and since
        `a-withdrawal-is-the-subjects-to-lift` a service may not re-provision
        over one — `/consent/admin/shares` answers 409. `onboarding-seam`
        provisions exactly this offer's wildcard as a service, so a withdrawal
        left here made that flow fail for a reason that had nothing to do with
        it, whether or not this flow passed.

        So this removes the fixture state instead, which is what
        `onboarding-seam` and `fail-closed` already do for the same reason:
        *"an opt-out cannot be un-said through the API and should not be."*
        Scoped to this offer and this subject, and to the two consumer ids this
        flow writes — a broader delete would take another flow's rows with it.
        """
        s = self.settings
        if not self._wrote_rows:
            return
        dsn = f"{s.database_url.rstrip('/')}/connector_rec"
        try:
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM consent_requests "
                        "WHERE subject_id = %s AND offer_id = %s "
                        "AND consumer_id = ANY(%s)",
                        (s.data_subject_id, s.sharing_offer_id, ["*", OUTSIDER_DID]),
                    )
                    removed = cur.rowcount
                conn.commit()
            log.info("wildcard-admission cleanup: removed %d consent row(s)", removed)
        except psycopg.Error as exc:
            # Cleanup must not mask the flow's own verdict, but it must say so:
            # a silent failure here is the next flow's unexplained failure.
            log.warning(
                "wildcard-admission cleanup: could not remove its consent rows "
                "(%s) — a later flow may see this flow's state",
                exc,
            )
