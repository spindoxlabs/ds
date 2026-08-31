"""`E2E-06` — the fail-closed flow's own preconditions.

The live property this flow asserts cannot be unit-tested: it needs a real
process to go away. What *can* be pinned here is the reasoning that decides
whether the live observation counts — the classification of a refusal, and the
access-request clearing that makes a refusal attributable. Both are the parts
that were wrong, and both are cheap to get wrong again.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY
from ds_e2e.flows.fail_closed import (
    PDP_CACHE_MARGIN_S,
    Attempt,
    FailClosedFlow,
    _left_operands,
)
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _flow(settings: E2ESettings, http: MagicMock) -> FailClosedFlow:
    return FailClosedFlow(settings, http)


def _request(settings: E2ESettings, **overrides) -> dict:
    row = {
        "id": "req-1",
        "asset_id": settings.fail_closed_asset_id,
        "status": "finalized",
        "can_revoke": True,
    }
    row.update(overrides)
    return row


# ── the flow is reachable ────────────────────────────────────────────────────


def test_fail_closed_is_registered():
    """It was written and left out of the registry while it was one step short.

    `test_cli_exposes_every_registered_flow` covers the CLI half; this pins the
    registration itself, because an unregistered P0 check is a check that does
    not run."""
    assert FLOW_REGISTRY["fail-closed"] is FailClosedFlow


# ── classification: which refusals are evidence ──────────────────────────────


@pytest.mark.parametrize(
    "outcome,evidence",
    [
        ("terminated", True),
        ("unsettled", True),
        ("no-offer", True),
        ("not-started", False),
        ("agreed", False),
    ],
)
def test_only_a_provider_side_refusal_is_evidence(outcome, evidence):
    assert Attempt(outcome, 0).is_provider_refusal is evidence


def test_a_deduplication_409_fails_the_flow_instead_of_passing_it(settings):
    """**The regression this flow exists to avoid.**

    The connector answers 409 for an asset this consumer already holds, with the
    PDP up or down. A refusal assertion that only checked "no contract was
    agreed" would report *fails closed* while observing deduplication — and
    would pass against a running PDP, which is the one outcome that makes the
    whole flow meaningless."""
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear = MagicMock(return_value=True)
    flow._stop_pdp = MagicMock(return_value=None)
    flow._wait_silent = MagicMock(return_value=True)
    flow._wait_out_decision_cache = MagicMock()
    flow._start_exchange = MagicMock(
        return_value=Attempt(
            "not-started",
            409,
            detail={"detail": "Access for asset '…' was already requested"},
        )
    )

    result = FlowResult(flow_name="fail-closed")
    flow._assert_refusals_while_down(result, {})

    gate = next(s for s in result.steps if s.name == "negotiation fails closed")
    assert gate.status == "FAIL"
    assert not result.passed


def test_a_terminated_negotiation_is_accepted_as_fail_closed(settings):
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear = MagicMock(return_value=True)
    flow._stop_pdp = MagicMock(return_value=None)
    flow._wait_silent = MagicMock(return_value=True)
    flow._wait_out_decision_cache = MagicMock()
    flow._start_exchange = MagicMock(
        return_value=Attempt("terminated", 200, state="TERMINATED")
    )

    result = FlowResult(flow_name="fail-closed")
    flow._assert_refusals_while_down(result, {})

    gate = next(s for s in result.steps if s.name == "negotiation fails closed")
    assert gate.status == "PASS"


def test_an_agreement_during_the_outage_fails(settings):
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear = MagicMock(return_value=True)
    flow._stop_pdp = MagicMock(return_value=None)
    flow._wait_silent = MagicMock(return_value=True)
    flow._wait_out_decision_cache = MagicMock()
    flow._start_exchange = MagicMock(
        return_value=Attempt("agreed", 200, agreement_id="agreement-1")
    )

    result = FlowResult(flow_name="fail-closed")
    flow._assert_refusals_while_down(result, {})

    gate = next(s for s in result.steps if s.name == "negotiation fails closed")
    assert gate.status == "FAIL"


def test_the_outage_is_not_entered_when_the_clear_fails(settings):
    """A refusal after a failed clear is unattributable, so it is never sought.

    Stopping the PDP anyway would produce exactly the observation this flow must
    not trust, and would leave the container down for a step that cannot mean
    anything."""
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear = MagicMock(return_value=False)
    flow._stop_pdp = MagicMock(return_value=None)
    flow._wait_silent = MagicMock(return_value=True)
    flow._wait_out_decision_cache = MagicMock()
    flow._start_exchange = MagicMock()

    flow._assert_refusals_while_down(FlowResult(flow_name="fail-closed"), {})

    flow._stop_pdp.assert_not_called()
    flow._start_exchange.assert_not_called()


# ── the target must have something for the PDP to decide ─────────────────────


_PURPOSE_ONLY = {
    "@id": "offer-1",
    "permission": [
        {
            "action": "https://w3id.org/dsp/policy/Query",
            "constraint": [
                {
                    "leftOperand": "odrl:purpose",
                    "operator": "isAnyOf",
                    "rightOperand": [
                        "https://w3id.org/dsp/policy/purpose/GridMonitoring"
                    ],
                }
            ],
        }
    ],
}

_MEMBERSHIP_GATED = {
    "@id": "offer-2",
    "permission": [
        {
            "action": "https://w3id.org/dsp/policy/Query",
            "constraint": [
                {
                    "leftOperand": "https://w3id.org/dsp/policy/Membership",
                    "operator": "eq",
                    "rightOperand": "owner:example-org:member",
                },
                {
                    "leftOperand": "odrl:purpose",
                    "operator": "isAnyOf",
                    "rightOperand": [],
                },
            ],
        }
    ],
}


def test_an_offer_the_edc_decides_alone_fails_the_flow(settings):
    """**The defect this flow shipped with, as an assertion.**

    Its first target published only `odrl:purpose`, which `PurposeFunction`
    evaluates inside the EDC JVM. No `/internal/*` call means no PDP to be
    unreachable, so stopping one changed nothing and the flow reported a P0
    fail-open. Every other step passed, which is why this one exists."""
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._offer = MagicMock(return_value=_PURPOSE_ONLY)

    result = FlowResult(flow_name="fail-closed")
    assert flow._assert_offer_needs_the_pdp(result, {}) is False
    assert result.steps[-1].status == "FAIL"
    assert result.steps[-1].data["operands"] == ["odrl:purpose"]


def test_a_membership_gated_offer_is_a_valid_target(settings):
    """`Membership` is `AccessScopeFunction`, which calls the connector."""
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._offer = MagicMock(return_value=_MEMBERSHIP_GATED)

    result = FlowResult(flow_name="fail-closed")
    assert flow._assert_offer_needs_the_pdp(result, {}) is True
    assert result.steps[-1].data["constraints"] == [
        "https://w3id.org/dsp/policy/Membership"
    ]


def test_left_operands_reads_both_catalogue_shapes():
    """A shape this misses reads as "no constraint", which is the failing side —
    but only if it is read at all, so the tolerance is pinned rather than
    assumed."""
    assert _left_operands(
        {"odrl:permission": {"odrl:constraint": {"odrl:leftOperand": {"@id": "ds:X"}}}}
    ) == {"ds:X"}


def test_the_default_target_is_not_the_purpose_only_dataset(settings):
    """The grid operator's dataset is the one that has nothing for a PDP to say.

    Pinned because the setting's default is the whole fix, and the two asset ids
    are one edit apart."""
    assert settings.fail_closed_asset_id != settings.grid_operator_asset_id


# ── the cache window ─────────────────────────────────────────────────────────


def test_the_outage_outlasts_the_decision_cache(settings, monkeypatch):
    """A refusal observed inside the cache TTL is a refusal by nothing.

    Measured live: VERIFIED at ~10s of PDP downtime off a cached `true`,
    TERMINATED at ~75s. The wait is derived from the same variable the EDC
    containers are given, so the harness cannot wait a number the platform is
    not using."""
    slept: list[float] = []
    monkeypatch.setattr("ds_e2e.flows.fail_closed.time.sleep", slept.append)
    result = FlowResult(flow_name="fail-closed")

    _flow(settings, MagicMock(spec=HttpClient))._wait_out_decision_cache(result)

    assert slept == [settings.pdp_cache_ttl_s + PDP_CACHE_MARGIN_S]
    assert slept[0] > settings.pdp_cache_ttl_s
    assert result.steps[-1].status == "PASS"


def test_the_outage_is_abandoned_when_the_stopped_container_still_answers(settings):
    """`E2E_PDP_CONTAINER` and `connector_url` must name the same service.

    If they do not, the flow stopped something else and every refusal below
    would be attributed to a service nobody stopped."""
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear = MagicMock(return_value=True)
    flow._stop_pdp = MagicMock(return_value=None)
    flow._wait_silent = MagicMock(return_value=False)
    flow._wait_out_decision_cache = MagicMock()
    flow._start_exchange = MagicMock()

    result = FlowResult(flow_name="fail-closed")
    flow._assert_refusals_while_down(result, {})

    assert result.steps[-1].name == "pdp stopped"
    assert result.steps[-1].status == "FAIL"
    flow._start_exchange.assert_not_called()


# ── clearing: which requests are revoked ─────────────────────────────────────


def test_clear_revokes_this_consumers_live_request_for_the_asset(settings):
    http = MagicMock(spec=HttpClient)
    http.get.return_value = [_request(settings, id="req-live")]
    http.post.return_value = {"status": "revoked", "id": "req-live"}

    revoked, error = _flow(settings, http)._clear_access_requests({})

    assert error is None
    assert revoked == ["req-live"]
    assert http.post.call_args.args[0].endswith("/consumer/requests/req-live/revoke")


def test_clear_leaves_other_assets_alone(settings):
    """The consumer's requests for other datasets are not this flow's to revoke.

    `smoke` and the `uc*` flows hold live requests on other datasets; revoking
    them would make this flow break the ones after it, which is the failure the
    bracket exists to avoid."""
    http = MagicMock(spec=HttpClient)
    http.get.return_value = [
        _request(settings, id="other", asset_id=settings.grid_operator_asset_id)
    ]

    revoked, error = _flow(settings, http)._clear_access_requests({})

    assert (revoked, error) == ([], None)
    http.post.assert_not_called()


def test_clear_uses_the_connectors_own_can_revoke(settings):
    """Not a second copy of the deduplication status set.

    A status list restated here drifts the moment the connector adds one — the
    `GOV-01` shape. `can_revoke` is the connector's answer to the same
    question."""
    http = MagicMock(spec=HttpClient)
    http.get.return_value = [
        _request(settings, id="spent", status="terminated", can_revoke=False)
    ]

    revoked, error = _flow(settings, http)._clear_access_requests({})

    assert (revoked, error) == ([], None)
    http.post.assert_not_called()


def test_clear_reports_a_revoke_that_did_not_revoke(settings):
    """A 200 that does not say `revoked` is not a revocation.

    Reporting success here is how the 409 gets back in: the next negotiation is
    refused by our own connector and the refusal reads as the provider's."""
    http = MagicMock(spec=HttpClient)
    http.get.return_value = [_request(settings, id="req-1")]
    http.post.return_value = {"status": "pending"}

    revoked, error = _flow(settings, http)._clear_access_requests({})

    assert revoked == []
    assert error and "req-1" in error


def test_clear_reports_an_unreachable_connector(settings):
    http = MagicMock(spec=HttpClient)
    http.get.side_effect = RuntimeError("connection refused")

    revoked, error = _flow(settings, http)._clear_access_requests({})

    assert revoked == []
    assert error and "could not list access requests" in error


def test_clear_step_fails_the_flow_when_it_cannot_clear(settings):
    http = MagicMock(spec=HttpClient)
    http.get.side_effect = RuntimeError("connection refused")
    result = FlowResult(flow_name="fail-closed")

    cleared = _flow(settings, http)._clear(result, {}, "prior access requests cleared")
    assert cleared is False
    assert result.steps[-1].status == "FAIL"


# ── the flow releases what it took ───────────────────────────────────────────


def test_the_flow_releases_its_request_after_recovery(settings):
    """Re-runnable in place (`REV-03`), and it does not block the next flow.

    A finalized request left behind here is a 409 for whoever negotiates the
    same pair next — including this flow on a re-run."""
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._start_exchange = MagicMock(
        return_value=Attempt("agreed", 200, agreement_id="agreement-2")
    )
    flow._clear_access_requests = MagicMock(return_value=([], None))
    cleared: list[str] = []
    flow._clear = MagicMock(
        side_effect=lambda r, h, step: (cleared.append(step), True)[1]
    )

    result = FlowResult(flow_name="fail-closed")
    flow._assert_service_resumes(result, {})

    # One clear before the attempt (unreported — it repeats per retry), and the
    # reported release once the exchange has completed.
    assert flow._clear_access_requests.call_count == 1
    assert cleared == ["access request released"]
    assert result.passed


def test_recovery_retries_until_the_decision_cache_expires(settings, monkeypatch):
    """**The failure the first live run produced.**

    `AccessScopeFunction` cached the `false` it computed during the outage, so
    the first negotiation after the connector came back was refused by a
    decision taken while it was down — and the flow reported *"failing closed
    must be temporary, not permanent"* against a platform that had recovered.
    Recovery is bounded by the same cache as the refusal."""
    monkeypatch.setattr("ds_e2e.flows.fail_closed.time.sleep", lambda _: None)
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear_access_requests = MagicMock(return_value=([], None))
    flow._clear = MagicMock(return_value=True)
    flow._start_exchange = MagicMock(
        side_effect=[
            Attempt("terminated", 200, state="TERMINATED"),
            Attempt("terminated", 200, state="TERMINATED"),
            Attempt("agreed", 200, agreement_id="agreement-3"),
        ]
    )

    result = FlowResult(flow_name="fail-closed")
    flow._assert_service_resumes(result, {})

    assert flow._start_exchange.call_count == 3
    resumed = next(s for s in result.steps if s.name == "service resumes")
    assert resumed.status == "PASS"


def test_recovery_gives_up_after_the_cache_window(settings, monkeypatch):
    """A refusal that outlives the cache is the permanent one — and must fail.

    Retrying forever would turn "the platform never recovered" into a hang, so
    the deadline is the property, not the patience."""
    clock = iter([0.0, 0.0] + [float(n) for n in range(10, 2000, 10)])
    monkeypatch.setattr("ds_e2e.flows.fail_closed.time.sleep", lambda _: None)
    monkeypatch.setattr("ds_e2e.flows.fail_closed.time.monotonic", lambda: next(clock))
    http = MagicMock(spec=HttpClient)
    flow = _flow(settings, http)
    flow._clear_access_requests = MagicMock(return_value=([], None))
    flow._clear = MagicMock(return_value=True)
    flow._start_exchange = MagicMock(
        return_value=Attempt("terminated", 200, state="TERMINATED")
    )

    result = FlowResult(flow_name="fail-closed")
    flow._assert_service_resumes(result, {})

    resumed = next(s for s in result.steps if s.name == "service resumes")
    assert resumed.status == "FAIL"
    # It stopped, rather than retrying until the suite timed out.
    assert flow._start_exchange.call_count < 20


# ── The per-query gate (`E2E-16`, `X-6`'s other half) ─────────────────────────
#
# The live property needs a real control plane to go away. What is pinned here is
# what decides whether the live observation counts — that a refusal is
# **attributable to the PDP**, which is `E2E-05`'s lesson and not a hypothetical
# here: with the connector down, the EDC's policy monitor cannot evaluate consent
# either, so a terminated transfer would stop the query too and would look
# identical from outside.


def test_a_plane_that_serves_rows_fails_the_step(settings):
    """The failure the whole phase exists to detect."""
    http = MagicMock()
    http.post_raw.return_value = (200, {"count": 3, "items": [{}, {}, {}]})
    flow, result = _flow(settings, http), FlowResult(flow_name="t")

    flow._assert_per_query_refusals(result, {})

    assert [s.status for s in result.steps] == ["FAIL"]
    assert "served" in result.steps[0].detail


def test_the_measured_refusal_passes(settings):
    """`502 ds-connector unreachable`, which is what both planes actually answer."""
    http = MagicMock()
    http.post_raw.return_value = (502, {"detail": "ds-connector unreachable"})
    flow, result = _flow(settings, http), FlowResult(flow_name="t")

    flow._assert_per_query_refusals(result, {})

    assert [s.status for s in result.steps] == ["PASS"]


def test_a_refusal_for_another_reason_does_not_count(settings):
    """A 403 is also what an unrelated policy denial produces — and with the PDP
    down, a transfer the policy monitor terminated produces one too. Accepting any
    non-200 would let this pass without observing the gate at all."""
    http = MagicMock()
    http.post_raw.return_value = (403, {"detail": "no consent for this subject"})
    flow, result = _flow(settings, http), FlowResult(flow_name="t")

    flow._assert_per_query_refusals(result, {})

    assert [s.status for s in result.steps] == ["FAIL"]
    assert "not for want of the PDP" in result.steps[0].detail


def test_a_named_connector_failure_counts_whatever_the_status(settings):
    """A data plane may legitimately answer 403 for an undecidable request; what
    it may not do is refuse for a reason this flow cannot attribute."""
    http = MagicMock()
    http.post_raw.return_value = (403, {"detail": "ds-connector unreachable, denying"})
    flow, result = _flow(settings, http), FlowResult(flow_name="t")

    flow._assert_per_query_refusals(result, {})

    assert [s.status for s in result.steps] == ["PASS"]


def test_every_configured_data_plane_is_queried(settings):
    """`E2E-16` was blocked on `T-1` precisely because asserting this against one
    implementation is evidence about that implementation."""
    http = MagicMock()
    http.post_raw.return_value = (502, {"detail": "ds-connector unreachable"})
    _flow(settings, http)._assert_per_query_refusals(FlowResult(flow_name="t"), {})

    queried = {call[0][0] for call in http.post_raw.call_args_list}
    assert len(queried) == len(settings.data_planes) >= 2


def test_the_per_query_phase_runs_before_the_cache_wait():
    """Ordering is the evidence that the two gates are on different clocks.

    The negotiation gate reuses a decision for the access-scope TTL, so its
    assertion waits 75s. The data plane asks per query and caches nothing, so it
    must refuse at once — asserting it after the wait would prove nothing about
    which clock applied.
    """
    import inspect

    from ds_e2e.flows.fail_closed import FailClosedFlow

    source = inspect.getsource(FailClosedFlow._assert_refusals_while_down)
    assert source.index("_assert_per_query_refusals") < source.index(
        "_wait_out_decision_cache"
    )
