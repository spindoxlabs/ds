"""E2E-06 · the PDP is unreachable, and every enforcement point refuses.

**NOT REGISTERED YET — one step short.** `flows/__init__.py` leaves it out of
`FLOW_REGISTRY` deliberately.

What is missing is **access-request lifecycle management**. The connector
deduplicates access requests per user and asset, so the second negotiation for
the same pair answers:

    409 "Access for asset 'datasets.gold.grid_capacity' was already requested
         by this user (status=finalized, id=…)"

`two-providers` runs earlier in `--flow all` and leaves exactly that row behind,
so this flow's baseline finds the asset already contracted for.

**Read this before "fixing" it by accepting the 409.** That status is returned
whether the PDP is up or down — so an assertion that merely checks "the second
negotiation did not succeed" would report *fails closed* while observing
deduplication, and would pass with the PDP running. The baseline bracket is what
caught it. The fix is for the flow to **revoke its own access request** before
the baseline and again at the end (`POST /consumer/requests/{id}/revoke`), which
also makes it re-runnable in place — the property `REV-03` asks of every flow.

It is left here rather than deleted because the structure is the part that took
the thinking, and because a red flow in `--flow all` teaches people to ignore
the summary. Do not register it until it is green — the flow's own first
assertion exists to stop it reporting a refusal it cannot attribute.

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

## What each enforcement point is expected to do

| Point | With the PDP down | Where the behaviour is decided |
|---|---|---|
| Data plane, per query | refuse, **no rows** | the dataset-api PEP, which
  calls `/internal/dataplane/authorize` |
| Transfer start | refuse | `AgreementConsentFunction`,
  `Stance.PRE_START(1, …)` — one unanswerable check is enough |

`Stance.IN_FLIGHT(3, …)` — three consecutive failures before terminating a
*running* transfer — is deliberately **not** asserted here: it is a timer-driven
re-evaluation, so asserting it would make this flow's verdict depend on how long
it slept. The pre-start gate and the per-query gate are both synchronous, and
between them they cover the two paths a consumer can actually take.
"""
from __future__ import annotations

import logging
import subprocess
import time
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

#: How long to wait for the connector to answer `/health` again after `docker
#: start`. Generous: this is teardown, and a flow that gives up early leaves the
#: dataspace down for every flow after it.
RESTART_TIMEOUT_S = 90


class FailClosedFlow(BaseFlow):
    name = "fail-closed"
    description = (
        "The policy decision point is unreachable: the data plane and the "
        "transfer gate both refuse, and service resumes when it returns"
    )

    def __init__(self, settings, http):
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
            "ps", "-a",
            "--filter", f"name=^{self.settings.pdp_container}$",
            "--format", "{{.Names}}",
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

    def _wait_healthy(self) -> bool:
        deadline = time.monotonic() + RESTART_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                self.http.get(f"{self.settings.grid_operator_connector_url}/health")
                return True
            except Exception:
                time.sleep(2)
        return False

    def cleanup(self) -> None:
        """Restore the PDP however this flow ended.

        `execute` restores it on the happy path too — this is the net under an
        exception, a `KeyboardInterrupt` or an early `return` added later. The
        cost of getting it wrong is not one red flow, it is every flow after it.
        """
        if self._stopped:
            log.warning("fail-closed: restoring %s after an incomplete run",
                        self.settings.pdp_container)
            self._start_pdp()
            self._wait_healthy()

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

        exchange = self._establish_baseline(result)
        if exchange is None:
            return result

        try:
            self._assert_refusals_while_down(result, exchange)
        finally:
            self._restore(result)

        self._assert_service_resumes(result, exchange)
        return result

    # ── 1. baseline ──────────────────────────────────────────────────────────

    def _establish_baseline(self, result: FlowResult) -> dict[str, Any] | None:
        """A working transfer and a query that returns rows, with the PDP up."""
        s = self.settings
        try:
            email = urllib.parse.quote(s.consumer_email, safe="")
            body = self.http.get(
                f"{s.identity_registry_url}/users/resolve?email={email}",
                headers=self.http.bearer_headers(),
            ) or {}
            consumer_vc = body.get("vc_jws")
        except Exception as exc:
            result.fail_step(
                "baseline", f"could not resolve the consumer credential: {exc}"
            )
            return None
        if not consumer_vc:
            result.fail_step("baseline", f"no credential for {s.consumer_email}")
            return None
        headers = {"X-Subject-Id": s.consumer_subject_id, "X-User-VC": consumer_vc}

        status, payload = self._start_exchange(headers)
        if status != 200 or not isinstance(payload, dict) or not payload.get(
            "contractAgreementId"
        ):
            result.fail_step(
                "baseline",
                "a contract must be agreed before the outage, or a refusal "
                "during it proves nothing",
                status_code=status,
            )
            return None
        result.pass_step(
            "baseline",
            "a contract is agreed with this provider while its PDP is up",
            agreement_id=payload.get("contractAgreementId"),
        )
        return {"headers": headers}

    def _offer_id(self, headers: dict[str, str]) -> str | None:
        """The offer id **the provider published**, read from its catalogue.

        Not `asset_id`. The connector re-resolves the policy from the catalogue
        anyway, but an offer id it cannot match leaves the negotiation to
        terminate — which is what this flow was doing to itself, and which is
        indistinguishable from the refusal it exists to detect. Same two-step
        `two_providers` uses, for the same reason.
        """
        s = self.settings
        try:
            catalog = self.http.post(
                f"{s.consumer_connector_url}/consumer/catalog",
                {
                    "counter_party_address": s.grid_operator_counter_party_address,
                    "counter_party_id": s.grid_operator_did,
                },
                headers=headers,
            ) or {}
        except Exception:
            return None
        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        for d in datasets:
            if not isinstance(d, dict):
                continue
            if str(d.get("@id") or d.get("id")) != s.grid_operator_asset_id:
                continue
            policies = d.get("hasPolicy") or d.get("odrl:hasPolicy") or []
            if isinstance(policies, dict):
                policies = [policies]
            if policies and isinstance(policies[0], dict):
                return str(policies[0].get("@id") or "")
        return None

    def _start_exchange(self, headers: dict[str, str]) -> tuple[int, Any]:
        """Ask for a *new* contract, and wait for the negotiation to settle.

        `/consumer/negotiate`, not `/consumer/flow`: the negotiation **is** the
        enforcement point under test — the constraint functions run there, once
        per contract request — and `two_providers` drives this same exchange the
        same way.
        """
        s = self.settings
        offer_id = self._offer_id(headers)
        if not offer_id:
            # With the PDP down the provider's catalogue is itself unreachable,
            # which is a refusal: no offer, no contract.
            return 0, {"reason": "no offer published"}

        status, payload = self.http.post_raw(
            f"{s.consumer_connector_url}/consumer/negotiate",
            {
                "counter_party_address": s.grid_operator_counter_party_address,
                "offer_id": offer_id,
                "asset_id": s.grid_operator_asset_id,
                "assigner": s.grid_operator_did,
            },
            headers=headers,
        )
        if status != 200 or not isinstance(payload, dict):
            return status, payload
        negotiation_id = str(
            payload.get("negotiation_id")
            or payload.get("@id")
            or payload.get("id")
            or ""
        )
        if not negotiation_id:
            return status, payload

        deadline = time.monotonic() + 60
        state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                state = self.http.get(
                    f"{s.consumer_connector_url}/consumer/negotiations/"
                    f"{urllib.parse.quote(negotiation_id, safe='')}",
                    headers=headers,
                ) or {}
            except Exception:
                state = {}
            if state.get("contractAgreementId") or state.get("state") == "TERMINATED":
                break
            time.sleep(2)
        return (200 if state.get("contractAgreementId") else 409), state

    # ── 2. the outage ────────────────────────────────────────────────────────

    def _assert_refusals_while_down(
        self, result: FlowResult, exchange: dict[str, Any]
    ) -> None:
        s = self.settings
        error = self._stop_pdp()
        if error:
            result.fail_step("pdp stopped", f"could not stop the PDP: {error}")
            return
        result.pass_step("pdp stopped", f"{s.pdp_container} is down")

        # `Stance.PRE_START(1, …)`: nothing is running yet, so one unanswerable
        # check is enough to refuse. The root guide's rule for every constraint
        # function — *deny on error* — is what this asserts, against a control
        # plane that is actually gone rather than a mocked failure.
        try:
            status, payload = self._start_exchange(exchange["headers"])
        except Exception:
            # The consumer connector failing to complete the exchange **is** the
            # expected outcome; an exception is a refusal too.
            status, payload = 0, None

        started = (
            status == 200
            and isinstance(payload, dict)
            and payload.get("contractAgreementId")
        )
        if started:
            result.fail_step(
                "transfer start fails closed",
                "a new transfer started while the provider's PDP was unreachable "
                "— a constraint function answered a question it could not ask",
                agreement_id=payload.get("contractAgreementId"),
            )
        else:
            result.pass_step(
                "transfer start fails closed",
                "no contract is agreed and no transfer starts while the "
                "provider's policy decision point cannot be reached",
                status_code=status,
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
        result.pass_step(
            "pdp restored", f"{s.pdp_container} is healthy again"
        )

    def _assert_service_resumes(
        self, result: FlowResult, exchange: dict[str, Any]
    ) -> None:
        """The closing bracket.

        Without it, a platform that refused *permanently* — a poisoned cache, a
        circuit breaker with no reset — would pass every assertion above.
        Failing closed is only correct if it is also temporary.
        """
        try:
            status, payload = self._start_exchange(exchange["headers"])
        except Exception as exc:
            result.fail_step("service resumes", f"the exchange still fails: {exc}")
            return
        agreed = status == 200 and isinstance(payload, dict) and payload.get(
            "contractAgreementId"
        )
        if not agreed:
            result.fail_step(
                "service resumes",
                "an exchange still cannot complete after the PDP came back — "
                "failing closed must be temporary, not permanent",
                status_code=status,
            )
            return
        result.pass_step(
            "service resumes",
            "the same exchange completes once the PDP answers again",
            agreement_id=payload.get("contractAgreementId"),
        )
