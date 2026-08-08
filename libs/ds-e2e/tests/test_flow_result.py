"""E2E-01 and E2E-14 · the harness noticing its own silence.

Two ways this suite could report a healthy dataspace while asserting nothing:

- a flow that records **no steps** was `all([]) == True`, so it passed;
- a service the flow calls but does not health-check raised out of `run_all`,
  ending the run with a traceback and **zero** results.

Both are the ledger's closing rule — *a green check is not a check that ran* —
inside the harness whose job is to catch exactly that, which is why they are
tested together.
"""
from __future__ import annotations

from ds_e2e.config import E2ESettings
from ds_e2e.flows.api_contract import PUBLIC_ROUTES, ApiContractFlow
from ds_e2e.models import FlowResult


# ── E2E-01 ───────────────────────────────────────────────────────────────────

def test_a_flow_that_recorded_nothing_does_not_pass():
    """The counterfactual. `all([])` is `True`, so this used to be a PASS."""
    assert FlowResult(flow_name="empty").passed is False


def test_a_flow_with_one_passing_step_passes():
    result = FlowResult(flow_name="f")
    result.pass_step("health", "reachable")
    assert result.passed is True


def test_a_single_failure_fails_the_flow():
    result = FlowResult(flow_name="f")
    result.pass_step("health", "reachable")
    result.fail_step("perimeter", "a public route answered 401")
    assert result.passed is False


def test_the_empty_flow_serialises_as_failed():
    """The JSON output feeds the summary and CI, so it must agree."""
    assert FlowResult(flow_name="empty").as_dict()["status"] == "FAIL"


# ── E2E-14 ───────────────────────────────────────────────────────────────────

def test_every_service_the_flow_calls_is_health_checked():
    """The gate must cover the routes, not a hand-kept list beside them.

    `dataset-api` is in `PUBLIC_ROUTES` and was absent from the health list, so
    an unreachable data plane escaped the gate and took the whole suite down
    with a `ConnectError` instead of failing one step.
    """
    flow = ApiContractFlow(E2ESettings(_env_file=None), http=None)
    checked = set(flow._services_this_flow_calls())
    probed = {service for service, *_ in PUBLIC_ROUTES}
    assert probed <= checked, f"probed but never health-checked: {probed - checked}"


def test_the_data_plane_is_among_them():
    """Named explicitly — it is the one that was missing, and the one whose
    absence is most likely to recur, since it is the only service the stack does
    not always start."""
    flow = ApiContractFlow(E2ESettings(_env_file=None), http=None)
    assert "dataset-api" in flow._services_this_flow_calls()


def test_the_health_list_is_not_hardcoded():
    """A guard on the fix rather than the symptom.

    If someone replaces the derivation with a literal list, this fails — which
    is the only thing that stops `E2E-14` recurring the next time a route is
    added for a new service.
    """
    import inspect

    source = inspect.getsource(ApiContractFlow._services_this_flow_calls)
    assert "PUBLIC_ROUTES" in source
    assert "SWEPT_SERVICES" in source


# ── ENV-09 · a 5xx is not evidence of a fail-open ────────────────────────────

def test_the_cross_owner_step_separates_an_outage_from_a_fail_open():
    """`user-authority` reported a P1 whose cause was an outage.

    Its refusal branch accepted 401/403 and read *everything else* as "deleted
    or was allowed to delete" — so on a stack whose provider EDC was down it
    named a cross-owner delete that had merely 500'd at the handler. The two
    failures even arrive together: the same unreachable EDC is what made the
    perimeter allow the request (`ENV-09`), so the harness pointed at the
    consequence and not the cause.

    Asserted on the source, because reproducing it needs a broken stack — which
    is exactly the condition the branch exists for.
    """
    import inspect

    from ds_e2e.flows.user_authority import UserAuthorityFlow

    source = inspect.getsource(UserAuthorityFlow.execute)
    assert "status >= 500" in source, (
        "the cross-owner refusal branch no longer separates a 5xx from an "
        "allowed write — a broken provider surface will read as a fail-open"
    )
    assert "says nothing about owner scoping" in source
