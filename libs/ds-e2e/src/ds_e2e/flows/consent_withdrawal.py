"""A data subject withdraws consent while a transfer is running — `E2E-05`, `D-17`.

Rulebook [Personal data](../../../../docs/rulebook/personal-data.md) `D-17`:
*revocation terminates a **running** transfer, not merely future ones.* It was
recorded **Enforced** and asserted live by nothing.

## What this asserts that no other flow did

`smoke` has the closest thing, and it differs on both axes:

* **A different actor.** It revokes the *consumer's access request*
  (`POST /consumer/requests/{id}/revoke`) — a consumer withdrawing its own ask.
  `D-17` is about a **data subject** withdrawing consent, which is a different
  person, a different endpoint and a different obligation.
* **A different assertion.** It polls the *query* for a 403 and passes on
  *"stale transfer cannot query after revoke"* — the per-query gate, not
  termination. `TERMINATED` is asserted in one other file, `fail_closed.py`, and
  there it is a **negotiation**.

So nothing observed a running transfer process reaching a terminal state, and
this flow does: read back from the **provider EDC's** management API, because a
403 is also what an unrelated policy denial produces and inferring termination
from it would pass against a platform that never terminated anything.

## The two layers, and why both are checked here

Withdrawal stops data and tears down the transfer by **different mechanisms on
different clocks**, and conflating them is what made `D-17` look simpler than it
is:

1. **The data gate is immediate.** `/internal/dataplane/authorize` reads the
   consent table per query, so the next query is refused within milliseconds.
2. **The teardown is the policy monitor's.** `services/connector/api/v1/consent.py`
   deliberately does *not* terminate from the connector — EDC's policy monitor
   re-evaluates each started transfer against the agreement policy, and
   `AgreementConsentFunction.inFlight` answers from that same consent table. So
   the transfer terminates on the monitor's **next pass** and on no other event.

**A wrong turn worth recording**, because the next reader will take it too.
EDC's policy monitor has `edc.policy.monitor.period`, defaulting to `PT1H` and
set nowhere in this platform, and `PolicyMonitorManagerImpl.checkPolicies`
reschedules itself on exactly that period — so it reads as *the* enforcement
window, and `D-17` as green against a teardown up to an hour away. It is not.
**Measured** on 2026-08-09 at both `PT1M` and `PT1H`, four minutes after boot so
no start-up pass was in play: termination landed **3s** after withdrawal both
times, through the `policy.monitor` scope either way. Whatever schedules that
evaluation, it is not that setting, and configuring it would have been a knob
with a documented meaning it does not have. So this flow bounds its wait with a
plain harness timeout and **reports the latency it saw** rather than checking it
against a number that would not mean what it says.

## Re-runnable in place

`flows/__init__.py` claims every flow is (`REV-03`). This one grants consent,
consumes it and restores it, and clears its own access request — so a second run
starts where the first began rather than on a 409 that would look like a refusal
(`E2E-06` paid for that one).
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any

from ds_e2e.cleanup import EDC_CONTEXT, edc_headers
from ds_e2e.consent import legal_basis
from ds_e2e.flows.base import BaseFlow
from ds_e2e.http import HttpError
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
STARTED_TRANSFER_STATES = {"STARTED"}

#: States that mean the provider stopped the transfer. `TERMINATED` is the one
#: the monitor produces; `DEPROVISIONED`/`COMPLETED` are accepted because a
#: transfer that finished on its own before the monitor ran is not evidence
#: *against* `D-17` — but the flow says which it saw, so a run that never
#: actually observed a termination cannot read as one that did.
STOPPED_TRANSFER_STATES = {"TERMINATED", "TERMINATING", "DEPROVISIONED", "COMPLETED"}


class ConsentWithdrawalFlow(BaseFlow):
    name = "consent-withdrawal"
    description = (
        "A data subject withdraws consent while a transfer is running: data stops "
        "at once and the provider's transfer process reaches a terminal state"
    )

    # ── EDC reads ────────────────────────────────────────────────────────────

    def _provider_transfers(self) -> list[dict[str, Any]]:
        """Every transfer process the **provider** EDC holds.

        The provider's, not the consumer's: the policy monitor runs on the side
        that owns the agreement, so that is where a termination originates.
        Reading the consumer's view instead would assert on DSP propagation too,
        and a flow that fails should name one thing.

        `EDC_CONTEXT` and `edc_headers` come from `cleanup`, which already had
        the request shape right. Writing a second one here got it **wrong** —
        the body omitted `"@type": "QuerySpec"`, EDC answered `InvalidRequest`,
        and the `isinstance(body, list)` guard below turned that into *no
        transfers* rather than an error. The flow then reported that the provider
        was not watching a transfer it was watching perfectly well.
        """
        status, body = self.http.post_raw(
            f"{self.settings.edc_provider_management_url}/v3/transferprocesses/request",
            EDC_CONTEXT,
            headers=edc_headers(self.settings),
        )
        if status != 200:
            log.warning(
                "provider EDC management refused the transfer query: HTTP %s %s",
                status,
                body,
            )
            return []
        if not isinstance(body, list):
            # **Loud.** This is the shape the missing `@type` produced, and
            # returning `[]` for it is indistinguishable from a provider with no
            # transfers — which is a state this flow reads as *stopped*.
            log.warning("provider EDC answered a non-list transfer query: %s", body)
            return []
        return body

    @staticmethod
    def _state_of(transfer: dict[str, Any]) -> str:
        # EDC's JSON-LD comes back compacted or prefixed depending on the
        # context it was asked with; `cleanup.py` reads both and so does this.
        return str(transfer.get("state") or transfer.get("edc:state") or "")

    def _provider_transfer_for(self, transfer_id: str) -> dict[str, Any] | None:
        """The provider-side transfer for the consumer transfer we started.

        Joined on **`correlationId`**, which is the consumer's transfer-process
        id — measured, after matching on the agreement found nothing. The two
        sides mint different ids for *both* the agreement and the transfer, and
        `correlationId` is the only field either side carries that names the
        other's. Matching on `contractId` compares the provider's local agreement
        id against the consumer's, which are different UUIDs for one agreement.
        """
        for tp in self._provider_transfers():
            correlation = tp.get("correlationId") or tp.get("edc:correlationId")
            if correlation == transfer_id:
                return tp
        return None

    # ── Consent state ────────────────────────────────────────────────────────

    def _consenting_subjects(self, svc: dict[str, str], dataset_id: str) -> list[str]:
        """Everyone whose consent currently backs this consumer for this dataset.

        Asked the way the **policy monitor** asks it — `subject_id` omitted. That
        is not a detail: `AgreementConsentFunction.inFlight` calls
        `consent.check("", dataset, consumer, purposes)`, so what decides whether
        a running transfer keeps its lawful basis is *whether anyone at all still
        consents*, not whether the withdrawing subject does.
        """
        payload = self.http.get(
            f"{self.settings.connector_url}/internal/consent/check?"
            + urllib.parse.urlencode(
                {
                    "dataset_id": dataset_id,
                    "consumer_id": self.settings.consumer_did,
                    "purpose": self.settings.consented_purpose,
                }
            ),
            headers=svc,
        ) or {}
        return [s for s in (payload.get("subject_ids") or []) if isinstance(s, str)]

    def _set_admin_share(
        self, svc: dict[str, str], subject_id: str, enabled: bool
    ) -> None:
        """Provision or withdraw a subject's standing consent, as an operator.

        **No `legal_basis` on withdrawal** — `ds_e2e.consent` says why: a person
        may always stop, and a caller that supplies proof in order to stop would
        hide a regression in that rule. Granting requires it.
        """
        body: dict[str, Any] = {
            "subject_id": subject_id,
            "offer_id": self.settings.sharing_offer_id,
            "enabled": enabled,
        }
        if enabled:
            body["legal_basis"] = legal_basis("e2e-consent-withdrawal restore")
        self.http.post(
            f"{self.settings.connector_url}/consent/admin/shares", body, headers=svc
        )

    # ── The flow ─────────────────────────────────────────────────────────────

    def execute(self) -> FlowResult:  # noqa: C901 - linear, read top to bottom
        s = self.settings
        result = FlowResult(flow_name=self.name)

        if not self._check_health(result):
            return result

        # **A deadline, not a platform window.** See
        # `consent_withdrawal_timeout_seconds`:
        # the obvious candidate, `edc.policy.monitor.period`, does *not* govern
        # this — measured at both `PT1M` and `PT1H`, termination landed 3s after
        # withdrawal either way. So this bounds the wait and the flow reports the
        # latency it actually saw rather than checking it against a number that
        # would not mean what it says.
        deadline_budget = s.consent_withdrawal_timeout_seconds

        try:
            self.http.acquire_service_token()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result
        svc = self.http.bearer_headers()

        try:
            self.http.post(f"{s.connector_url}/provider/sync", {}, headers=svc)
        except Exception as exc:
            result.fail_step("provider sync", str(exc))
            return result

        consumer_vc, subject_vc = self._fetch_credentials(result, svc)
        if consumer_vc is None:
            return result
        consumer_headers = {
            "X-Subject-Id": s.consumer_subject_id,
            "X-User-VC": consumer_vc,
        }
        subject_headers = {"X-Subject-Id": s.data_subject_id, "X-User-VC": subject_vc}

        # Start from no live request, or the negotiation below is answered by a
        # 409 dedup that reads exactly like a refusal (`E2E-06`).
        self._clear_access_requests(consumer_headers)
        result.pass_step(
            "prior access cleared",
            "this consumer holds no live access request, so the negotiation below "
            "reaches the provider",
        )

        # ── 1. Consent, then a live transfer ─────────────────────────────────

        if not self._grant(result, subject_headers):
            return result

        catalog_body = {
            "counter_party_address": s.counter_party_address,
            "counter_party_id": s.provider_did,
        }
        try:
            catalog = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/catalog",
                    catalog_body,
                    headers=consumer_headers,
                )
                or {}
            )
            dataset = self._select_dataset(catalog)
            if not dataset:
                result.fail_step("catalogue", "catalog has no datasets")
                return result
            asset_id = str(dataset.get("@id") or dataset.get("id") or s.asset_id)
        except Exception as exc:
            result.fail_step("catalogue", str(exc))
            return result

        # **Make this subject the last basis, and say so.**
        #
        # `D-17`'s termination fires when a withdrawal removes the *final* consent
        # for this consumer and dataset — the monitor asks "does **anyone** still
        # consent", not "does this subject". So with another subject consenting,
        # a withdrawal correctly leaves the transfer running and removes only the
        # withdrawing subject's rows, and asserting termination would be
        # asserting a property the platform is right not to have.
        #
        # Found by running this flow inside the suite: standalone it passed
        # because this subject happened to be the only consenter; after `smoke`,
        # which provisions a scoped wildcard and leaves `consumer-user` consenting
        # too, the transfer legitimately did not terminate.
        #
        # So the precondition is established deliberately rather than inherited
        # from whatever ran before, and restored in `cleanup`.
        self._suspended: list[str] = [
            subject
            for subject in self._consenting_subjects(svc, asset_id)
            if subject != s.data_subject_id
        ]
        for subject in self._suspended:
            self._set_admin_share(svc, subject, enabled=False)
        result.pass_step(
            "sole consenter established",
            "this subject is the only remaining consent for this consumer and "
            "dataset, so their withdrawal is what empties the pool — the condition "
            "under which `D-17` claims a running transfer is terminated",
            suspended=self._suspended,
        )

        policy = self._policy(dataset)
        offer_purposes = self._offer_purposes(policy)
        declared = [
            p for p in offer_purposes if p.rsplit("/", 1)[-1] == s.consented_purpose
        ] or offer_purposes[:1]
        try:
            negotiated = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/negotiate",
                    {
                        "counter_party_address": s.counter_party_address,
                        "offer_id": str(policy.get("@id") or f"{asset_id}#offer"),
                        "asset_id": asset_id,
                        "assigner": s.provider_did,
                        "odrl_policy": policy or None,
                        "declared_purpose": declared,
                        "justification_ref": "e2e-consent-withdrawal",
                    },
                    headers=consumer_headers,
                )
                or {}
            )
            negotiation_id = negotiated["negotiation_id"]
        except Exception as exc:
            result.fail_step("negotiate", str(exc))
            return result

        negotiation = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/negotiations/"
            f"{urllib.parse.quote(negotiation_id, safe='')}",
            lambda p: (
                p.get("state") in FINAL_NEGOTIATION_STATES
                and bool(p.get("contractAgreementId"))
            ),
            headers=consumer_headers,
        )
        agreement_id = negotiation.get("contractAgreementId")
        if not agreement_id:
            result.fail_step(
                "negotiate",
                "negotiation did not finalize",
                state=negotiation.get("state"),
            )
            return result
        result.pass_step(
            "negotiate",
            "a contract is agreed while consent stands",
            agreement_id=agreement_id,
        )

        try:
            transfer = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/transfer",
                    {
                        "contract_agreement_id": agreement_id,
                        "counter_party_address": s.counter_party_address,
                        "asset_id": asset_id,
                        "connector_id": s.provider_did,
                    },
                    headers=consumer_headers,
                )
                or {}
            )
            transfer_id = transfer["transfer_id"]
        except Exception as exc:
            result.fail_step("transfer starts", str(exc))
            return result

        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/transfers/"
            f"{urllib.parse.quote(transfer_id, safe='')}",
            lambda p: p.get("state") in STARTED_TRANSFER_STATES,
            headers=consumer_headers,
        )
        if state.get("state") not in STARTED_TRANSFER_STATES:
            result.fail_step(
                "transfer starts",
                "transfer did not reach STARTED",
                transfer_id=transfer_id,
                state=state.get("state"),
            )
            return result
        # The EDR is its own read, and it carries the **shared** DSP agreement
        # id. `contractAgreementId` from the negotiation is this side's *local*
        # id and means nothing to the provider (`EDCL-06`) — a query sending it
        # is refused as `agreement_unknown`, which from here would look exactly
        # like the withdrawal working before the subject had withdrawn anything.
        edr = (
            self.http.get(
                f"{s.consumer_connector_url}/consumer/edr/"
                f"{urllib.parse.quote(transfer_id, safe='')}",
                headers=consumer_headers,
            )
            or {}
        )
        edr_token = str(edr.get("authorization") or "")
        shared_agreement_id = str(edr.get("agreement_id") or agreement_id)
        if not edr_token:
            result.fail_step(
                "transfer starts", "the EDR carries no authorization token"
            )
            return result
        result.pass_step(
            "transfer starts",
            "an EDR-gated transfer is running",
            transfer_id=transfer_id,
        )

        # The provider must be watching it, or there is nothing for a withdrawal
        # to terminate and every assertion below would be vacuous.
        provider_tp = self._provider_transfer_for(transfer_id)
        if provider_tp is None:
            result.fail_step(
                "provider is watching",
                "no provider-side transfer for this agreement",
                agreement_id=agreement_id,
            )
            return result
        result.pass_step(
            "provider is watching",
            "the provider holds a transfer process for this agreement, so the policy "
            "monitor has something to re-evaluate",
            provider_state=self._state_of(provider_tp),
        )

        # ── 2. The transfer genuinely works, before withdrawal ───────────────
        #
        # Without this the whole flow is satisfiable by a transfer that never
        # served a row: "no data after withdrawal" is not evidence unless there
        # was data before it.

        def query() -> tuple[int, Any]:
            return self.http.post_raw(
                f"{s.dataset_api_url}/query",
                {"sql": f"SELECT * FROM {asset_id}", "limit": 10},
                headers={
                    "Authorization": edr_token,
                    "Edc-Contract-Agreement-Id": shared_agreement_id,
                    "Edc-Transfer-Process-Id": transfer_id,
                    "Edc-Purpose": s.consented_purpose,
                },
            )

        status, payload = query()
        rows_before = payload.get("count", 0) if isinstance(payload, dict) else 0
        if status != 200 or rows_before < 1:
            result.fail_step(
                "data flows before withdrawal",
                "the consented transfer served no rows, so nothing below would mean "
                "anything",
                status_code=status,
            )
            return result
        result.pass_step(
            "data flows before withdrawal",
            "the running transfer serves rows while consent stands",
            rows=rows_before,
        )

        # ── 3. The subject withdraws ─────────────────────────────────────────
        #
        # An **explicit opt-out for this consumer**, not merely the absence of a
        # grant. `D-15`: a per-party row overrides the scoped wildcard, and the
        # dev fixtures leave a wildcard behind (`smoke` provisions one through
        # `/consent/admin/shares`). Withdrawing without naming the consumer would
        # leave that wildcard authorising the very transfer this flow is about.
        try:
            self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {
                    "offer_id": s.sharing_offer_id,
                    "consumer_id": s.consumer_did,
                    "enabled": False,
                },
                headers=subject_headers,
            )
        except HttpError as exc:
            result.fail_step(
                "subject withdraws", f"HTTP {exc.status}", response=exc.body
            )
            return result
        withdrawn_at = time.time()
        result.pass_step(
            "subject withdraws",
            "the data subject withdrew consent for this consumer — the subject's own "
            "act, not the consumer revoking its access request",
            subject=s.data_subject_id,
            consumer=s.consumer_did,
        )

        # ── 4. Data stops at once ────────────────────────────────────────────

        # **Fewer rows, or a refusal — not necessarily a 403.**
        #
        # Consent gates by *row filter*, per subject: the data plane asks
        # `/internal/dataplane/authorize` and applies the filter it returns, so
        # one subject withdrawing removes that subject's rows and leaves
        # everyone else's. A 403 happens only when nobody is left authorised.
        #
        # This step demanded a 403 and passed standalone — in isolation this
        # subject is the only consenter, so removing them empties the result.
        # Run after `smoke`, which provisions a scoped wildcard for other
        # parties, the same withdrawal correctly leaves rows and the step
        # failed. It was asserting a property of the whole dataset while
        # claiming one about a person, and the fixture hid the difference.
        # (`D-15` is fine, measured directly: an explicit opt-out beats the
        # wildcard and `/internal/consent/check` answers *"consumer explicitly
        # opted out"*.)
        gate_deadline = time.time() + 30
        gate_status, rows_after = 0, rows_before
        while time.time() < gate_deadline:
            gate_status, gate_payload = query()
            rows_after = (
                gate_payload.get("count", 0) if isinstance(gate_payload, dict) else 0
            )
            if gate_status == 403 or rows_after < rows_before:
                break
            time.sleep(1)
        if gate_status != 403 and rows_after >= rows_before:
            result.fail_step(
                "data stops immediately",
                "the data plane served this subject's rows after they withdrew — "
                f"{rows_after} rows, against {rows_before} before",
                status_code=gate_status,
                rows_before=rows_before,
                rows_after=rows_after,
            )
            return result
        result.pass_step(
            "data stops immediately",
            (
                "the per-query gate refused outright"
                if gate_status == 403
                else f"the row filter dropped this subject: {rows_before} rows "
                f"→ {rows_after}"
            )
            + f", {time.time() - withdrawn_at:.0f}s after withdrawal — the "
            "consent table read per query, not the transfer teardown",
            rows_before=rows_before,
            rows_after=rows_after,
        )

        # ── 5. And the transfer process is torn down ─────────────────────────
        #
        # `D-17`'s actual claim, and the one nothing asserted. Read from the
        # provider EDC: a 403 above is also what an unrelated policy denial
        # produces, so inferring termination from it would pass against a
        # platform that terminates nothing.

        deadline = withdrawn_at + deadline_budget
        final_state = self._state_of(provider_tp)
        while time.time() < deadline:
            current = self._provider_transfer_for(transfer_id)
            final_state = self._state_of(current) if current else "GONE"
            if final_state in STOPPED_TRANSFER_STATES or final_state == "GONE":
                break
            time.sleep(3)

        if final_state not in STOPPED_TRANSFER_STATES and final_state != "GONE":
            result.fail_step(
                "running transfer terminated",
                f"the provider's transfer process is still {final_state!r} "
                f"{time.time() - withdrawn_at:.0f}s after the subject withdrew "
                f"consent. Data is refused per query, so nothing leaked — but "
                "`D-17` claims the transfer itself is terminated, and it was not. "
                "Measured latency when this was written was 3s; raise the timeout "
                "only if you can show the teardown is merely slower, not absent.",
                agreement_id=agreement_id,
                state=final_state,
                timeout_seconds=deadline_budget,
            )
            return result
        result.pass_step(
            "running transfer terminated",
            f"the provider's transfer process reached {final_state} "
            f"{time.time() - withdrawn_at:.0f}s after the subject withdrew — read "
            "from the provider EDC, not inferred from a refused query",
            state=final_state,
            agreement_id=agreement_id,
        )
        return result

    # ── Setup and teardown ───────────────────────────────────────────────────

    def _grant(self, result: FlowResult, subject_headers: dict[str, str]) -> bool:
        s = self.settings
        try:
            rows = (
                self.http.post(
                    f"{s.connector_url}/consent/my/shares",
                    {
                        "offer_id": s.sharing_offer_id,
                        "consumer_id": s.consumer_did,
                        "enabled": True,
                    },
                    headers=subject_headers,
                )
                or []
            )
        except HttpError as exc:
            result.fail_step("consent granted", f"HTTP {exc.status}", response=exc.body)
            return False
        rows = rows if isinstance(rows, list) else [rows]
        if not rows:
            result.fail_step("consent granted", "the offer expanded to no consent rows")
            return False
        result.pass_step(
            "consent granted",
            "the data subject consents, so there is something to withdraw",
            consent_ids=[r.get("id") for r in rows],
        )
        return True

    def _clear_access_requests(self, consumer_headers: dict[str, str]) -> None:
        s = self.settings
        try:
            requests = (
                self.http.get(
                    f"{s.consumer_connector_url}/consumer/requests",
                    headers=consumer_headers,
                )
                or []
            )
        except Exception:
            return
        for item in requests:
            if item.get("status") in {"revoked", "terminated"}:
                continue
            request_id = item.get("id")
            if not request_id:
                continue
            try:
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/requests/"
                    f"{urllib.parse.quote(str(request_id), safe='')}/revoke",
                    {"reason": "e2e-consent-withdrawal setup"},
                    headers=consumer_headers,
                )
            except Exception:  # noqa: BLE001 - best effort; the negotiation checks
                log.debug("could not clear access request %s", request_id)

    def cleanup(self) -> None:
        """Restore the consent this flow withdrew, so the next run starts level.

        `run_flow` calls this in a `finally` (`E2E-06`), so it also runs when the
        flow failed halfway — which is when leaving a subject's consent withdrawn
        would be most confusing for whoever runs the suite next.
        """
        s = self.settings
        try:
            self.http.acquire_service_token()
            svc = self.http.bearer_headers()
            _, subject_vc = self._fetch_credentials(
                FlowResult(flow_name=self.name), svc
            )
            if not subject_vc:
                return
            self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {
                    "offer_id": s.sharing_offer_id,
                    "consumer_id": s.consumer_did,
                    "enabled": True,
                },
                headers={"X-Subject-Id": s.data_subject_id, "X-User-VC": subject_vc},
            )
            # And every subject whose consent this flow suspended to make itself
            # observable. Leaving them withdrawn would silently narrow the pool
            # for every later run — the flow would still pass, and would have
            # stopped proving anything about a *last* basis.
            for subject in getattr(self, "_suspended", []):
                self._set_admin_share(svc, subject, enabled=True)
        except Exception:  # noqa: BLE001 - cleanup must not mask the flow's own verdict
            log.warning(
                "consent-withdrawal cleanup could not restore the subject's consent"
            )
