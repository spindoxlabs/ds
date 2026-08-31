"""E2E-06 · the PDP is unreachable, and the negotiation gate refuses.

The last P0 on the ledger, and the one property no unit test can establish:
**when the policy decision point is down, does the platform deny?**

Rulebook `X-6` says the data plane must fail closed when the control plane is
unreachable, and the root guide states the rule the constraint functions live
under — *a constraint function must deny on error. Returning `true` when an
input is missing or a call fails is the defect class this codebase has the most
of.* Both are asserted here against a control plane that is actually stopped,
rather than against a mocked failure, because the thing being tested is what
happens to a **real** exchange when a **real** process goes away.

## Why the outage is bracketed

The flow proves the same request **succeeds, then is refused, then succeeds
again**. A refusal on its own proves nothing — a broken fixture, an expired
credential or a wrong asset id all produce one, and every one of them would make
this flow green while testing nothing. The baseline and the recovery are what
make the middle mean "because the PDP was down".

That is also why recovery is asserted rather than merely attempted: a flow that
leaves the dataspace broken makes every flow after it fail for reasons that have
nothing to do with them.

## Why a refusal is classified before it is believed

The bracket is necessary and **not sufficient**. The connector deduplicates
access requests per user and asset, so a second negotiation for a pair this
consumer already holds answers:

    409 "Access for asset 'datasets.gold.grid_capacity' was already requested
         by this user (status=finalized, id=…)"

That status comes back whether the PDP is up or down. An assertion that merely
checked *"the second negotiation did not succeed"* would therefore report
**fails closed** while observing deduplication — and would pass with the PDP
running, which is the one thing this flow must never do. It is not hypothetical:
`two-providers` runs earlier in `--flow all` and leaves exactly that row behind,
and the baseline bracket is what caught it.

So every exchange attempt returns an `Attempt` naming *who* refused
(`Attempt.outcome`), and only a refusal from the **provider side** —
`terminated`, `unsettled` or `no-offer` — is accepted as evidence. A
`not-started` is the consumer's own connector declining to open a negotiation,
and it fails this flow rather than passing it.

`_clear_access_requests` is the other half: this flow revokes its own requests
for the asset before each attempt, so the question it asks the provider is one
the consumer would otherwise be allowed to ask. It is also what makes the flow
re-runnable in place — the property `REV-03` asks of every flow — and it clears
`two-providers`' leftovers on the way past.

## Two things this flow got wrong, both found by running it

**1. The target must be a dataset whose offer has a PDP-backed constraint.**
This flow first negotiated for the grid operator's `datasets.gold.grid_capacity`
— chosen because it is the one exchange with no consent gate, so a baseline
costs one call. That convenience deleted the subject of the test. Its published
offer carries **only** `odrl:purpose`, and `PurposeFunction` evaluates that
inside the EDC JVM: no `/internal/*` call, so no PDP to be unreachable. The flow
reported a contract agreed with the PDP down and read as a **P0 fail-open**;
what it had actually found was a negotiation that never asks.

Only two constraint functions call ds-connector, and the target must carry one:
`AccessScopeFunction` (`{ns}Membership` → `GET /internal/participants/check`) and
`ConsentStatusFunction` / `AgreementConsentFunction` (`{ns}ConsentStatus` →
`GET /internal/consent/check`). The REC's `datasets.gold.om_weather_features` is
membership-gated and **not** consent-gated, so it needs the PDP and its baseline
still costs one call. `_assert_offer_needs_the_pdp` pins this in the flow rather
than in a comment, because "the fixture quietly stopped constraining anything" is
not a failure any other step here can see.

**2. The outage must outlast the decision cache.** `AccessScopeFunction` caches
each answer for `ds.access.scope.cache.ttl.seconds` (default 60). Measured on the
running stack: with the REC connector stopped, a negotiation at ~10s of downtime
reached **VERIFIED** off a cached `true`; the same negotiation at ~75s
**TERMINATED** with the `Membership` constraint unfulfilled. Both are correct
behaviour, and a flow that does not wait is asserting on the cache — the same
"green check that did not check" this ledger keeps finding. `PDP_CACHE_MARGIN_S`
is the margin over the configured TTL, and the wait is reported as a step so the
output says how long the platform was blind.

## What each enforcement point is expected to do

| Point | With the PDP down | Asserted here |
|---|---|---|
| Contract negotiation | refuse | **yes** — `AccessScopeFunction`, deny on error |
| Data plane, per query | refuse, no rows | **no** — see below |

**The per-query gate is deliberately not asserted here, and that is a gap, not a
completed row.** Asserting it against `services/dataset-api-mock` would be
evidence about the mock: the real PEP is the celine `dataset-api`, and until
`T-1` runs the flows against both data planes a green per-query refusal here
would say nothing about the one that is deployed. The root guide's own warning:
*a green run is only evidence about the thing that actually ran.* The mock's own
`_authorize` does deny on an unreachable connector, and its unit suite covers
that; what is missing is the live assertion against the deployed PEP.

`Stance.IN_FLIGHT(3, …)` — three consecutive failures before terminating a
*running* transfer — is deliberately not asserted either: it is a timer-driven
re-evaluation, so asserting it would make this flow's verdict depend on how long
it slept. The negotiation gate is synchronous, and it is the gate every consumer
passes through first.
"""

from __future__ import annotations

import logging
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from ds_e2e.config import E2ESettings
from ds_e2e.flows.base import BaseFlow
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

#: How long to wait for the connector to answer `/health` again after `docker
#: start`. Generous: this is teardown, and a flow that gives up early leaves the
#: dataspace down for every flow after it.
RESTART_TIMEOUT_S = 90

#: Seconds to wait *beyond* `pdp_cache_ttl_s` before asserting a refusal.
#: The TTL bounds how long a cached decision is served; the margin covers the
#: clock the EDC measures it on and the round trip after it. A refusal observed
#: inside the TTL is a refusal by nothing.
PDP_CACHE_MARGIN_S = 15

#: How long to wait for the stopped container's HTTP surface to actually stop
#: answering. `docker stop` returns when the process is signalled, not when the
#: socket is closed.
PDP_SILENCE_TIMEOUT_S = 30

#: Gap between recovery attempts. Recovery is bounded by the same decision
#: cache as the refusal — the `false` computed during the outage outlives it —
#: so the closing bracket retries rather than sleeping the whole TTL, and
#: passes as soon as the platform actually recovers.
RECOVERY_RETRY_S = 10

#: Constraint left operands whose EDC function calls ds-connector's
#: `/internal/*` API — the only ones whose evaluation a stopped PDP can change.
#: `AccessScopeFunction` → `/internal/participants/check`, and
#: `ConsentStatusFunction` → `/internal/consent/check`. `odrl:purpose` is
#: **not** here on purpose: `PurposeFunction` decides it inside the EDC JVM, so
#: an offer carrying only that has no PDP to fail closed on.
PDP_BACKED_OPERANDS = ("Membership", "ConsentStatus")

#: Refusals that came from the **provider side** — the only ones that are
#: evidence about its policy decision point. `not-started` is excluded on
#: purpose; see the module docstring.
PROVIDER_REFUSALS = frozenset({"terminated", "unsettled", "no-offer"})


def _left_operands(offer: dict[str, Any]) -> set[str]:
    """Every constraint left operand in a published ODRL offer.

    Tolerant of the two shapes the catalogue answers in — a single object or a
    list, `constraint` or `odrl:constraint` — because the point is to notice
    what is *there*, and a shape this misses reads as "no constraint", which is
    the failing side. Full IRIs are kept: the caller matches on the suffix, so
    it works whether the term arrived expanded or prefixed.
    """

    def _as_list(value: Any) -> list[Any]:
        if isinstance(value, dict):
            return [value]
        return value if isinstance(value, list) else []

    operands: set[str] = set()
    for key in ("permission", "odrl:permission", "prohibition", "obligation"):
        for rule in _as_list(offer.get(key)):
            if not isinstance(rule, dict):
                continue
            for ckey in ("constraint", "odrl:constraint"):
                for constraint in _as_list(rule.get(ckey)):
                    if not isinstance(constraint, dict):
                        continue
                    left = constraint.get("leftOperand") or constraint.get(
                        "odrl:leftOperand"
                    )
                    if isinstance(left, dict):
                        left = left.get("@id") or left.get("@value")
                    if left:
                        operands.add(str(left))
    return operands


@dataclass(frozen=True)
class Attempt:
    """One attempt at a contract, and **which side** decided the answer.

    `outcome` is the whole point of this type. A bare status code cannot
    distinguish the provider's constraint function refusing from our own
    connector declining to ask it, and those two are the difference between this
    flow proving something and this flow proving nothing.

    - ``agreed`` — a contract exists. The only non-refusal.
    - ``terminated`` — the negotiation ran and the provider ended it without an
      agreement. **The refusal under test.**
    - ``unsettled`` — the negotiation ran and never settled. No contract, so it
      is a refusal, but the observed state is reported rather than assumed.
    - ``no-offer`` — the provider's catalogue published no matching offer. Also
      a refusal: no offer, no contract. Only meaningful inside the bracket,
      which is why the baseline demands an offer first.
    - ``not-started`` — **our** connector refused to open a negotiation (409
      deduplication, 422, 5xx). Says nothing about the provider.
    """

    outcome: str
    status: int
    agreement_id: str | None = None
    state: str | None = None
    detail: Any = None

    @property
    def agreed(self) -> bool:
        return self.outcome == "agreed"

    @property
    def is_provider_refusal(self) -> bool:
        return self.outcome in PROVIDER_REFUSALS


#: Statuses that name the PDP's absence rather than a policy outcome. `502` is
#: what both data planes answer with — a bad gateway *is* the honest code for a
#: dependency that did not respond.
_PDP_UNREACHABLE_STATUS = frozenset({502, 503, 504})


def _names_the_pdp(detail: str) -> bool:
    """Does the refusal say the connector was the thing missing?

    Accepted alongside the status because a data plane is entitled to answer
    `403` for an undecidable request; what it may not do is refuse for a reason
    this flow cannot distinguish from an unrelated denial.
    """
    lowered = detail.lower()
    return "connector" in lowered and (
        "unreachable" in lowered or "unavailable" in lowered or "timeout" in lowered
    )


class FailClosedFlow(BaseFlow):
    name = "fail-closed"
    description = (
        "The policy decision point is unreachable: the negotiation gate "
        "refuses, and service resumes when it returns"
    )
    rules = ("A-11", "X-6", "X-6b", "X-6c")

    #: Set when the per-query baseline granted consent, so `cleanup` withdraws
    #: exactly what this flow added and nothing it inherited.
    _granted_consent = False

    def __init__(self, settings: E2ESettings, http: HttpClient) -> None:
        super().__init__(settings, http)
        self._stopped = False

    # ── docker control ───────────────────────────────────────────────────────

    def _docker(self, *args: str) -> tuple[int, str]:
        proc = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=60
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    def _container_exists(self) -> bool:
        code, out = self._docker(
            "ps",
            "-a",
            "--filter",
            f"name=^{self.settings.pdp_container}$",
            "--format",
            "{{.Names}}",
        )
        return code == 0 and self.settings.pdp_container in out

    def _stop_pdp(self) -> str | None:
        code, out = self._docker("stop", self.settings.pdp_container)
        if code != 0:
            return out
        self._stopped = True
        return None

    def _start_pdp(self) -> str | None:
        code, out = self._docker("start", self.settings.pdp_container)
        if code != 0:
            return out
        self._stopped = False
        return None

    def _pdp_answers(self) -> bool:
        try:
            self.http.get(f"{self.settings.connector_url}/health")
            return True
        except Exception:
            return False

    def _wait_healthy(self) -> bool:
        deadline = time.monotonic() + RESTART_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._pdp_answers():
                return True
            time.sleep(2)
        return False

    def _wait_silent(self) -> bool:
        """`docker stop` returned; wait for the HTTP surface to actually close.

        This is also what pins `pdp_container` to `connector_url`: if the two
        name different services the URL keeps answering, and the flow says so
        instead of attributing a refusal to a service nobody stopped.
        """
        deadline = time.monotonic() + PDP_SILENCE_TIMEOUT_S
        while time.monotonic() < deadline:
            if not self._pdp_answers():
                return True
            time.sleep(1)
        return False

    def cleanup(self) -> None:
        """Restore the PDP however this flow ended.

        `execute` restores it on the happy path too — this is the net under an
        exception, a `KeyboardInterrupt` or an early `return` added later. The
        cost of getting it wrong is not one red flow, it is every flow after it,
        which is why `runner.run_flow` calls this in a `finally` for every flow
        rather than leaving it to each one to remember.
        """
        if self._stopped:
            log.warning(
                "fail-closed: restoring %s after an incomplete run",
                self.settings.pdp_container,
            )
            self._start_pdp()
            self._wait_healthy()

        # And withdraw the consent the per-query baseline granted (`E2E-16`).
        # **Only if this flow granted it** — the subject may hold a standing
        # grant from `smoke` or the fixtures, and withdrawing that would leave
        # every later run starting from a state this flow invented. Ordered after
        # the PDP restart because the connector has to be up to accept it.
        if self._granted_consent:
            s = self.settings
            try:
                self.http.acquire_service_token()
                svc = self.http.bearer_headers()
                self.http.post(
                    f"{s.connector_url}/consent/my/shares",
                    {
                        "offer_id": s.sharing_offer_id,
                        "consumer_id": s.consumer_did,
                        "enabled": False,
                    },
                    headers={
                        "X-Subject-Id": s.data_subject_id,
                        "X-User-VC": self._resolve_user_vc(s.data_subject_email, svc),
                    },
                )
            except Exception:  # noqa: BLE001 - must not mask the flow's verdict
                log.warning("fail-closed: could not withdraw the consent it granted")
            finally:
                self._granted_consent = False

    # ── the flow ─────────────────────────────────────────────────────────────

    def execute(self) -> FlowResult:
        result = FlowResult(flow_name=self.name)
        s = self.settings

        if not self._container_exists():
            # **Fail, do not skip.** A P0 check that silently skips is the
            # defect this whole ledger keeps finding. This flow needs the Docker
            # topology, which is the one `task docker:restart` + `task e2e:all`
            # documents; under `task dev:*` the connector is a host process and
            # cannot be stopped by name.
            result.fail_step(
                "pdp is controllable",
                f"container {s.pdp_container!r} not found — this "
                "flow stops the provider connector, so it needs the Docker "
                "topology (task docker:restart), not the host-process one",
            )
            return result
        result.pass_step(
            "pdp is controllable",
            f"{s.pdp_container} is present and can be stopped",
        )

        headers = self._consumer_headers(result)
        if headers is None:
            return result

        if not self._assert_offer_needs_the_pdp(result, headers):
            return result

        if not self._clear(result, headers, "prior access requests cleared"):
            return result

        if not self._establish_baseline(result, headers):
            return result

        # `E2E-16`: a live transfer on the consent-gated asset, established while
        # the PDP is up, so the per-query gate has something to refuse during the
        # outage. `None` fails a step of its own and stops the flow.
        query_headers = self._establish_query_baseline(result, headers)
        if query_headers is None:
            return result

        try:
            self._assert_refusals_while_down(result, headers, query_headers)
        finally:
            self._restore(result)

        self._assert_service_resumes(result, headers)
        return result

    # ── access-request lifecycle ─────────────────────────────────────────────

    def _clear_access_requests(
        self, headers: dict[str, str], asset_id: str | None = None
    ) -> tuple[list[str], str | None]:
        """Revoke every live access request this consumer holds for the asset.

        Returns ``(revoked_ids, error)``. Revoking is not tidiness: it is what
        makes the next negotiation a question the provider gets to answer,
        rather than one our own connector answers with a 409 (see the module
        docstring). It also deletes the consumer's transfer rows for the asset,
        which is the other half of the deduplication check.

        The predicate is the connector's **own** `can_revoke`, not a copy of its
        deduplication status set. A second holder of that vocabulary here would
        drift the moment the connector added a status — the `GOV-01` shape, in a
        harness.
        """
        s = self.settings
        try:
            requests = (
                self.http.get(
                    f"{s.consumer_connector_url}/consumer/requests", headers=headers
                )
                or []
            )
        except Exception as exc:
            return [], f"could not list access requests: {exc}"
        if not isinstance(requests, list):
            return [], f"unexpected /consumer/requests payload: {requests!r}"

        revoked: list[str] = []
        for item in requests:
            if not isinstance(item, dict):
                continue
            if item.get("asset_id") != (asset_id or s.fail_closed_asset_id):
                continue
            if not item.get("can_revoke"):
                continue
            request_id = str(item.get("id") or "")
            if not request_id:
                continue
            encoded = urllib.parse.quote(request_id, safe="")
            try:
                body = (
                    self.http.post(
                        f"{s.consumer_connector_url}/consumer/requests/{encoded}/revoke",
                        {"reason": "e2e-fail-closed"},
                        headers=headers,
                    )
                    or {}
                )
            except Exception as exc:
                return revoked, f"could not revoke {request_id}: {exc}"
            if body.get("status") != "revoked":
                return revoked, (
                    f"revoke of {request_id} answered {body.get('status')!r}"
                )
            revoked.append(request_id)
        return revoked, None

    def _clear(self, result: FlowResult, headers: dict[str, str], step: str) -> bool:
        """`_clear_access_requests` as an assertion.

        A clear that fails silently is how the 409 gets back in: the next
        attempt is refused by our own connector and the refusal reads as the
        provider's. So it is a step, and a failure to clear ends the flow.
        """
        revoked, error = self._clear_access_requests(headers)
        if error:
            result.fail_step(
                step,
                "could not clear this consumer's access requests for "
                f"{self.settings.fail_closed_asset_id} — without that, a "
                f"refusal cannot be attributed to the provider: {error}",
                revoked=revoked or None,
            )
            return False
        result.pass_step(
            step,
            "this consumer holds no live access request for "
            f"{self.settings.fail_closed_asset_id}, so the next negotiation "
            "reaches the provider",
            revoked=revoked or None,
        )
        return True

    # ── 1. baseline ──────────────────────────────────────────────────────────

    def _consumer_headers(self, result: FlowResult) -> dict[str, str] | None:
        s = self.settings
        try:
            email = urllib.parse.quote(s.consumer_email, safe="")
            body = (
                self.http.get(
                    f"{s.identity_registry_url}/users/resolve?email={email}",
                    headers=self.http.bearer_headers(),
                )
                or {}
            )
            consumer_vc = body.get("vc_jws")
        except Exception as exc:
            result.fail_step(
                "consumer credential",
                f"could not resolve the consumer credential: {exc}",
            )
            return None
        if not consumer_vc:
            result.fail_step(
                "consumer credential", f"no credential for {s.consumer_email}"
            )
            return None
        return {"X-Subject-Id": s.consumer_subject_id, "X-User-VC": consumer_vc}

    def _establish_baseline(self, result: FlowResult, headers: dict[str, str]) -> bool:
        """A contract agreed with the PDP up, so a refusal later means something."""
        attempt = self._start_exchange(headers)
        if not attempt.agreed:
            result.fail_step(
                "baseline",
                "a contract must be agreed before the outage, or a refusal "
                "during it proves nothing",
                outcome=attempt.outcome,
                status_code=attempt.status or None,
                state=attempt.state,
                response=attempt.detail,
            )
            return False
        result.pass_step(
            "baseline",
            "a contract is agreed with this provider while its PDP is up",
            agreement_id=attempt.agreement_id,
        )
        return True

    def _offer(
        self, headers: dict[str, str], asset_id: str | None = None
    ) -> dict[str, Any] | None:
        """The offer **the provider published**, read from its catalogue.

        The id is not `asset_id`. The connector re-resolves the policy from the
        catalogue anyway, but an offer id it cannot match leaves the negotiation
        to terminate — which is what this flow was doing to itself, and which is
        indistinguishable from the refusal it exists to detect. Same two-step
        `two_providers` uses, for the same reason.
        """
        s = self.settings
        try:
            catalog = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/catalog",
                    {
                        "counter_party_address": s.counter_party_address,
                        "counter_party_id": s.provider_did,
                    },
                    headers=headers,
                )
                or {}
            )
        except Exception:
            return None
        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        for d in datasets:
            if not isinstance(d, dict):
                continue
            if str(d.get("@id") or d.get("id")) != (asset_id or s.fail_closed_asset_id):
                continue
            policies = d.get("hasPolicy") or d.get("odrl:hasPolicy") or []
            if isinstance(policies, dict):
                policies = [policies]
            if policies and isinstance(policies[0], dict):
                return policies[0]
        return None

    def _assert_offer_needs_the_pdp(
        self, result: FlowResult, headers: dict[str, str]
    ) -> bool:
        """The published offer must carry a constraint the PDP decides.

        **This is the step that would have caught the first version of this
        flow.** It targeted an offer whose only constraint was `odrl:purpose`,
        which the EDC evaluates in-process — so no PDP was consulted, stopping
        one changed nothing, and the flow reported a fail-open. Every other step
        passed.

        Read from the catalogue rather than from `governance.yaml`, because what
        the EDC evaluates is what the provider published, and the two can differ
        — that is `GOV-04`'s whole subject.
        """
        offer = self._offer(headers)
        if not offer:
            result.fail_step(
                "the offer is decided by the pdp",
                "the provider publishes no offer for "
                f"{self.settings.fail_closed_asset_id}",
            )
            return False
        operands = _left_operands(offer)
        backed = sorted(
            o for o in operands if any(o.endswith(name) for name in PDP_BACKED_OPERANDS)
        )
        if not backed:
            result.fail_step(
                "the offer is decided by the pdp",
                "no constraint on this offer is evaluated by ds-connector, so "
                "stopping it cannot refuse anything — this flow would report "
                "fail-open while testing a negotiation that never asks",
                operands=sorted(operands),
                pdp_backed=list(PDP_BACKED_OPERANDS),
            )
            return False
        result.pass_step(
            "the offer is decided by the pdp",
            "the offer carries a constraint whose EDC function calls "
            "ds-connector, so there is a decision the outage can take away",
            constraints=backed,
        )
        return True

    def _start_exchange(
        self, headers: dict[str, str], asset_id: str | None = None
    ) -> Attempt:
        """Ask for a *new* contract, and report **who** decided the answer.

        `/consumer/negotiate`, not `/consumer/flow`: the negotiation **is** the
        enforcement point under test — the constraint functions run there, once
        per contract request — and `two_providers` drives this same exchange the
        same way.
        """
        s = self.settings
        asset = asset_id or s.fail_closed_asset_id
        offer = self._offer(headers, asset)
        offer_id = str((offer or {}).get("@id") or "")
        if not offer_id:
            # With the PDP down the provider's catalogue answer is itself a
            # refusal: no offer, no contract. The baseline proves the offer was
            # there, which is what stops this reading as a broken fixture.
            return Attempt("no-offer", 0, detail="no offer published for the asset")

        status, payload = self.http.post_raw(
            f"{s.consumer_connector_url}/consumer/negotiate",
            {
                "counter_party_address": s.counter_party_address,
                "offer_id": offer_id,
                "asset_id": asset,
                "assigner": s.provider_did,
            },
            headers=headers,
        )
        negotiation_id = ""
        if status == 200 and isinstance(payload, dict):
            negotiation_id = str(
                payload.get("negotiation_id")
                or payload.get("@id")
                or payload.get("id")
                or ""
            )
        if not negotiation_id:
            # Our own connector never opened a negotiation. A 409 here is
            # deduplication, and it answers the same way with the PDP running —
            # so it is not evidence, it is a broken precondition.
            return Attempt("not-started", status, detail=payload)

        deadline = time.monotonic() + s.poll_timeout
        state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                state = (
                    self.http.get(
                        f"{s.consumer_connector_url}/consumer/negotiations/"
                        f"{urllib.parse.quote(negotiation_id, safe='')}",
                        headers=headers,
                    )
                    or {}
                )
            except Exception:
                state = {}
            if state.get("contractAgreementId") or state.get("state") == "TERMINATED":
                break
            time.sleep(s.poll_interval)

        agreement_id = state.get("contractAgreementId")
        observed = state.get("state")
        if agreement_id:
            return Attempt(
                "agreed", 200, agreement_id=str(agreement_id), state=observed
            )
        if observed == "TERMINATED":
            return Attempt("terminated", 200, state=observed)
        return Attempt("unsettled", 200, state=observed, detail=state or None)

    # ── the per-query gate (`E2E-16`, `X-6`'s other half) ────────────────────
    #
    # `X-6` has two enforcement points and this flow used to assert one. The
    # **negotiation** gate refuses a contract while the PDP is unreachable, which
    # everything above covers. The **per-query** gate is the data plane asking
    # `/internal/dataplane/authorize` for every query and denying when the answer
    # cannot be had — and nothing asserted it live, because the PEP in this
    # topology used to be the mock alone, so a green refusal would have been
    # evidence about the mock (`E2E-16` said exactly this, and it was right).
    #
    # `T-1` removed that objection: **one EDR is accepted by both data planes**,
    # measured, so this asserts the refusal on each and names which.
    #
    # **It needs the consent-gated asset, not this flow's usual one.** Two
    # measurements decided that: `datasets.gold.om_weather_features` does not
    # exist on the real celine `dataset-api` (`400 unknown dataset`), and on the
    # mock it is served by `_plain_query` — the deliberate no-dataspace path for
    # data with no subject behind it — which never calls `authorize` at all. A
    # refusal there would prove nothing about the gate. `datasets.silver.meters_15m`
    # is consent-gated, exists on both, and both refuse it without a credential.

    def _query(self, url: str, headers: dict[str, str]) -> tuple[int, Any]:
        return self.http.post_raw(
            f"{url}/query",
            {"sql": f"SELECT * FROM {self.settings.asset_id}", "limit": 10},
            headers=headers,
        )

    def _establish_query_baseline(
        self, result: FlowResult, headers: dict[str, str]
    ) -> dict[str, str] | None:
        """A live transfer serving rows from every data plane, before the outage.

        Returns the query headers, or `None` having failed a step. Without rows
        flowing first, "refused during the outage" is satisfiable by a transfer
        that never worked — the same hole `consent-withdrawal` had to close.
        """
        s = self.settings
        svc = self.http.bearer_headers()
        subject_vc = self._resolve_user_vc(s.data_subject_email, svc)
        subject = {"X-Subject-Id": s.data_subject_id, "X-User-VC": subject_vc}
        try:
            self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {
                    "offer_id": s.sharing_offer_id,
                    "consumer_id": s.consumer_did,
                    "enabled": True,
                },
                headers=subject,
            )
        except Exception as exc:
            result.fail_step("query baseline", f"could not grant consent: {exc}")
            return None
        self._granted_consent = True

        # **Clear this asset's requests first, or the negotiation is answered by
        # a 409 dedup** — which `_start_exchange` reports as *not agreed*, i.e.
        # exactly like the refusal this flow exists to detect. `E2E-06` paid for
        # that once already; the clearing above it filters on
        # `fail_closed_asset_id`, so the consent-gated asset needed its own pass.
        #
        # Found by the suite, not standalone: `smoke` and `consent-withdrawal`
        # both negotiate this asset and run before this flow, so a leftover
        # request is the normal case in a full run and absent in a solo one.
        self._clear_access_requests(headers, asset_id=s.asset_id)

        exchange = self._start_exchange(headers, asset_id=s.asset_id)
        if not exchange.agreed or not exchange.agreement_id:
            result.fail_step(
                "query baseline",
                "no agreement for the consent-gated asset, so there is no EDR to "
                "present during the outage",
                outcome=exchange.outcome,
                state=exchange.state,
            )
            return None

        try:
            transfer = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/transfer",
                    {
                        "contract_agreement_id": exchange.agreement_id,
                        "counter_party_address": s.counter_party_address,
                        "asset_id": s.asset_id,
                        "connector_id": s.provider_did,
                    },
                    headers=headers,
                )
                or {}
            )
            transfer_id = transfer["transfer_id"]
            self.http.poll_until(
                f"{s.consumer_connector_url}/consumer/transfers/"
                f"{urllib.parse.quote(transfer_id, safe='')}",
                lambda p: p.get("state") == "STARTED",
                headers=headers,
            )
            edr = (
                self.http.get(
                    f"{s.consumer_connector_url}/consumer/edr/"
                    f"{urllib.parse.quote(transfer_id, safe='')}",
                    headers=headers,
                )
                or {}
            )
        except Exception as exc:
            result.fail_step("query baseline", f"no EDR-gated transfer: {exc}")
            return None

        token = str(edr.get("authorization") or "")
        if not token:
            result.fail_step("query baseline", "the EDR carries no authorization token")
            return None
        query_headers = {
            "Authorization": token,
            # The **shared** DSP agreement id, which the provider knows; the
            # negotiation's `contractAgreementId` is this side's local one and is
            # refused as unknown (`EDCL-06`).
            "Edc-Contract-Agreement-Id": str(edr.get("agreement_id") or ""),
            "Edc-Transfer-Process-Id": transfer_id,
            "Edc-Purpose": s.consented_purpose,
        }

        for label, url in s.data_planes:
            status, payload = self._query(url, query_headers)
            rows = payload.get("count", 0) if isinstance(payload, dict) else 0
            if status != 200 or rows < 1:
                result.fail_step(
                    "query baseline",
                    f"{label} served no rows while the PDP was up, so a refusal "
                    "during the outage would prove nothing",
                    status_code=status,
                    data_plane=label,
                )
                return None
        result.pass_step(
            "query baseline",
            "a live transfer serves rows from every data plane while the PDP is up",
            data_planes=[label for label, _ in s.data_planes],
            transfer_id=transfer_id,
        )
        return query_headers

    def _assert_per_query_refusals(
        self, result: FlowResult, query_headers: dict[str, str]
    ) -> None:
        """Every data plane refuses while the PDP is unreachable — `E2E-16`.

        **No cache to wait out here, and that is the point of asserting it
        separately.** The negotiation gate reuses a decision for
        `ds.access.scope.cache.ttl.seconds`, which is why the step above this one
        waits 75s. The data plane asks per query and caches nothing, so the
        refusal is immediate — two enforcement points, two clocks, and conflating
        them is how `X-6` looked like one property.
        """
        served, unattributed, observed = [], [], []
        for label, url in self.settings.data_planes:
            status, payload = self._query(url, query_headers)
            rows = payload.get("count", 0) if isinstance(payload, dict) else 0
            body = payload.get("detail") if isinstance(payload, dict) else payload
            detail = str(body)
            short = label.split(" at ")[0]
            observed.append(f"{short}: {status} {detail[:70]}")
            if status == 200 and rows > 0:
                served.append(f"{short} served {rows} rows (HTTP {status})")
            elif not (status in _PDP_UNREACHABLE_STATUS or _names_the_pdp(detail)):
                # **A refusal has to be the gate's.** `E2E-05` is the same lesson:
                # a 403 is also what an unrelated policy denial produces, and here
                # the confound is real — with the PDP down, the EDC's policy
                # monitor cannot evaluate consent either, so a terminated transfer
                # would also stop the query and would look exactly like this.
                # Measured: both planes answer `502 ds-connector unreachable`.
                unattributed.append(f"{short}: HTTP {status} {detail[:60]}")
        log.info("per-query gate during the outage: %s", " | ".join(observed))
        if served:
            result.fail_step(
                "per-query gate fails closed",
                "a data plane served rows while the policy decision point was "
                "unreachable — it cannot have asked, and it answered anyway: "
                + "; ".join(served),
                observed=observed,
            )
            return
        if unattributed:
            result.fail_step(
                "per-query gate fails closed",
                "a data plane refused, but not for want of the PDP — so this run "
                "did not observe the gate. The likeliest other cause is the "
                "transfer having been terminated by the policy monitor, which "
                "also cannot reach consent while the connector is down: "
                + "; ".join(unattributed),
                observed=observed,
            )
            return
        result.pass_step(
            "per-query gate fails closed",
            "every data plane refused the query while ds-connector was down — "
            "asserted on the real celine dataset-api and on the mock, not "
            "inferred from one of them, and with no cache to wait out",
            observed=observed,
        )

    # ── 2. the outage ────────────────────────────────────────────────────────

    def _wait_out_decision_cache(self, result: FlowResult) -> None:
        """Outlast the decision cache, or assert nothing.

        The EDC's constraint functions reuse ds-connector's answer for
        `ds.access.scope.cache.ttl.seconds`. Inside that window a negotiation
        succeeds off a cached `true` and the platform is **correct** to let it —
        measured on the running stack: VERIFIED at ~10s of downtime, TERMINATED
        at ~75s. A flow that skips this wait asserts on the cache and calls it
        the PDP.

        It is a step rather than a bare sleep because the length of the window
        in which the platform cannot fail closed is the interesting number here,
        and a step is where the run says it out loud.
        """
        blind_for = self.settings.pdp_cache_ttl_s + PDP_CACHE_MARGIN_S
        time.sleep(blind_for)
        result.pass_step(
            "decision cache expired",
            f"waited {blind_for}s — longer than the "
            f"{self.settings.pdp_cache_ttl_s}s decision cache, so the next "
            "negotiation must ask a PDP that is not there rather than reuse an "
            "answer from when it was",
            cache_ttl_s=self.settings.pdp_cache_ttl_s,
        )

    def _assert_refusals_while_down(
        self,
        result: FlowResult,
        headers: dict[str, str],
        query_headers: dict[str, str] | None = None,
    ) -> None:
        # Clear the baseline's own request **before** stopping the PDP: revoking
        # is a consumer-side operation, but the flow should not depend on that
        # while it is busy proving what happens when a service is missing.
        if not self._clear(result, headers, "baseline request revoked"):
            return

        s = self.settings
        error = self._stop_pdp()
        if error:
            result.fail_step("pdp stopped", f"could not stop the PDP: {error}")
            return
        if not self._wait_silent():
            result.fail_step(
                "pdp stopped",
                f"{s.pdp_container} was stopped but {s.connector_url} still "
                "answers /health — the container named by E2E_PDP_CONTAINER is "
                "not the connector this flow negotiates with, so any refusal "
                "below would be attributed to a service nobody stopped",
            )
            return
        result.pass_step(
            "pdp stopped",
            f"{s.pdp_container} is down and {s.connector_url} has stopped answering",
        )

        # **The per-query gate first, before the cache wait** (`E2E-16`). It
        # caches nothing, so it must refuse immediately — and asserting it before
        # the 75s wait is what shows the two gates are on different clocks rather
        # than one property observed twice.
        if query_headers is not None:
            self._assert_per_query_refusals(result, query_headers)

        self._wait_out_decision_cache(result)

        # The root guide's rule for every constraint function — *deny on error*
        # — asserted against a control plane that is actually gone rather than
        # against a mocked failure.
        try:
            attempt = self._start_exchange(headers)
        except Exception as exc:
            # The consumer connector failing to complete the exchange **is** the
            # expected outcome; an exception is a refusal too.
            attempt = Attempt("terminated", 0, detail=str(exc))

        if attempt.agreed:
            result.fail_step(
                "negotiation fails closed",
                "a contract was agreed while the provider's PDP was unreachable "
                "— a constraint function answered a question it could not ask",
                agreement_id=attempt.agreement_id,
            )
            return
        if not attempt.is_provider_refusal:
            # The trap this flow exists to avoid falling into. Reporting PASS
            # here would mean reporting *fails closed* while observing our own
            # connector's deduplication — which answers identically with the PDP
            # running.
            result.fail_step(
                "negotiation fails closed",
                "no negotiation reached the provider, so its refusal was never "
                "tested — this is our own connector declining to ask, and it "
                "answers the same way with the PDP up",
                outcome=attempt.outcome,
                status_code=attempt.status or None,
                response=attempt.detail,
            )
            return
        result.pass_step(
            "negotiation fails closed",
            "the negotiation reached the provider and no contract was agreed "
            "while its policy decision point could not be reached",
            outcome=attempt.outcome,
            state=attempt.state,
        )

    # ── 3. recovery ──────────────────────────────────────────────────────────

    def _restore(self, result: FlowResult) -> None:
        s = self.settings
        error = self._start_pdp()
        if error:
            result.fail_step("pdp restored", f"could not restart the PDP: {error}")
            return
        if not self._wait_healthy():
            result.fail_step(
                "pdp restored",
                f"{s.pdp_container} did not answer /health within "
                f"{RESTART_TIMEOUT_S}s — the stack is left degraded",
            )
            return
        result.pass_step("pdp restored", f"{s.pdp_container} is healthy again")

    def _assert_service_resumes(
        self, result: FlowResult, headers: dict[str, str]
    ) -> None:
        """The closing bracket.

        Without it, a platform that refused *permanently* — a poisoned cache, a
        circuit breaker with no reset — would pass every assertion above.
        Failing closed is only correct if it is also temporary.

        **Recovery is bounded by the same cache as the refusal, and this is
        where that was found.** `AccessScopeFunction` cached the `false` it
        computed during the outage, so the first negotiation after the connector
        came back was refused by a decision taken while it was down: the flow
        reported *"failing closed must be temporary, not permanent"* against a
        platform that had already recovered. So the deadline here is the cache
        TTL too, and the elapsed time is reported — because "how long after the
        PDP returns does service actually resume" is the number a reader of this
        flow wants, and it is not zero.

        Each attempt clears first: a refused negotiation leaves an access
        request behind, and the 409 that follows would read as the platform
        never recovering.
        """
        s = self.settings
        deadline = time.monotonic() + s.pdp_cache_ttl_s + PDP_CACHE_MARGIN_S
        started = time.monotonic()
        attempt = Attempt("unsettled", 0, detail="no attempt was made")
        while True:
            _, error = self._clear_access_requests(headers)
            if error:
                result.fail_step(
                    "service resumes",
                    "could not clear this consumer's access requests, so a "
                    f"refusal below could not be attributed: {error}",
                )
                return
            try:
                attempt = self._start_exchange(headers)
            except Exception as exc:
                attempt = Attempt("unsettled", 0, detail=str(exc))
            if attempt.agreed or time.monotonic() >= deadline:
                break
            time.sleep(RECOVERY_RETRY_S)
        elapsed = round(time.monotonic() - started)

        if not attempt.agreed:
            result.fail_step(
                "service resumes",
                "an exchange still cannot complete "
                f"{elapsed}s after the PDP came back, which is longer than the "
                f"{s.pdp_cache_ttl_s}s decision cache — failing closed must be "
                "temporary, not permanent",
                outcome=attempt.outcome,
                status_code=attempt.status or None,
                state=attempt.state,
                response=attempt.detail,
            )
            return
        result.pass_step(
            "service resumes",
            f"the same exchange completes {elapsed}s after the PDP answers "
            "again — the refusal was the outage, not a state the platform got "
            "stuck in",
            agreement_id=attempt.agreement_id,
            seconds=elapsed,
        )

        # Leave nothing for the next run — or for `two-providers`, which
        # negotiates the same pair and is refused by the row this flow would
        # otherwise leave behind (`REV-03`).
        self._clear(result, headers, "access request released")
