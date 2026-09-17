"""`E2E-05` — the consent-withdrawal flow's own preconditions.

The live property cannot be unit-tested: it needs a real transfer, a real
subject and a policy monitor that actually runs. What *can* be pinned is the
reasoning that decides whether the live observation counts — the window the flow
waits, and how it identifies the transfer it is watching. Both are the parts that
would make a green run mean nothing.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY
from ds_e2e.flows.consent_withdrawal import (
    STOPPED_TRANSFER_STATES,
    ConsentWithdrawalFlow,
)


@pytest.fixture
def settings(monkeypatch) -> E2ESettings:
    monkeypatch.delenv("EDC_POLICY_MONITOR_PERIOD", raising=False)
    return E2ESettings(_env_file=None)


def _flow(
    settings: E2ESettings, http: MagicMock | None = None
) -> ConsentWithdrawalFlow:
    return ConsentWithdrawalFlow(settings, http or MagicMock())


# ── The deadline ──────────────────────────────────────────────────────────────
#
# A harness timeout, not a mirror of a platform setting. The obvious candidate —
# `edc.policy.monitor.period`, EDC's `PT1H` default — does **not** govern this:
# measured at both `PT1M` and `PT1H`, four minutes after boot, termination landed
# 3s after withdrawal either way. Configuring it would have shipped a knob with a
# documented meaning it does not have, which is the `T-4` shape.


class TestTheDeadline:
    def test_it_is_generous_relative_to_the_measured_latency(self, settings):
        """3s measured, 120s allowed. A deadline near the measurement turns
        ordinary jitter into a red flow, and a red flow nobody believes is worse
        than no flow."""
        assert settings.consent_withdrawal_timeout_seconds >= 60

    def test_it_is_overridable_without_editing_the_flow(self, monkeypatch):
        monkeypatch.setenv("E2E_CONSENT_WITHDRAWAL_TIMEOUT_SECONDS", "5")
        assert E2ESettings(_env_file=None).consent_withdrawal_timeout_seconds == 5

    def test_the_flow_does_not_read_a_policy_monitor_period(self):
        """It did, and the setting does not mean what that implied.

        Re-introducing it would put a number in the output — *"within the 60s
        policy-monitor window"* — that reads as a measured property of the
        platform and is not one.
        """
        import inspect

        from ds_e2e.flows import consent_withdrawal

        source = inspect.getsource(consent_withdrawal.ConsentWithdrawalFlow)
        assert "policy_monitor_period" not in source


# ── Identifying the transfer ──────────────────────────────────────────────────


class TestFindingTheProviderTransfer:
    """The provider's view, through the provider connector.

    It used to be a query against the provider EDC's management API with the
    shared key. That port is not published and there is no key; the provider
    connector's `GET /internal/transfers/{id}/status` does the same lookup —
    by **correlationId**, the consumer's transfer id — against its own EDC.
    """

    def test_it_asks_the_provider_connector_by_the_consumer_transfer_id(self, settings):
        http = MagicMock()
        http.bearer_headers.return_value = {"Authorization": "Bearer t"}
        http.raw.return_value = (200, {"active": True, "edc_state": "STARTED"})
        flow = _flow(settings, http)

        found = flow._provider_transfer_for("consumer tp/A")

        assert flow._state_of(found) == "STARTED"
        method, url = http.raw.call_args[0][:2]
        assert method == "GET"
        assert url == (
            f"{settings.connector_url}/internal/transfers/consumer%20tp%2FA/status"
        )
        assert settings.consumer_connector_url not in url

    def test_a_transfer_the_provider_does_not_hold_is_none(self, settings):
        http = MagicMock()
        http.raw.return_value = (200, {"active": False, "reason": "transfer_not_found"})
        assert _flow(settings, http)._provider_transfer_for("x") is None

    def test_an_unreachable_edc_is_not_a_state(self, settings):
        """`edc_unreachable` is a deny with no state; reading it as one would
        report a stop nobody observed."""
        http = MagicMock()
        http.raw.return_value = (200, {"active": False, "reason": "edc_unreachable"})
        assert _flow(settings, http)._provider_transfer_for("x") is None

    @pytest.mark.parametrize(
        "answer", [(401, {"detail": "no"}), (500, "boom"), (200, ["not", "a", "dict"])]
    )
    def test_an_unreadable_answer_is_none_not_an_exception(self, settings, answer):
        """The caller loops on this; a refusal ends as a named failure."""
        http = MagicMock()
        http.raw.return_value = answer
        assert _flow(settings, http)._provider_transfer_for("x") is None

    def test_a_terminated_transfer_reads_as_terminated(self, settings):
        http = MagicMock()
        http.raw.return_value = (200, {"active": False, "edc_state": "TERMINATED"})
        flow = _flow(settings, http)
        assert flow._state_of(flow._provider_transfer_for("x")) == "TERMINATED"


# ── What counts as stopped ────────────────────────────────────────────────────


# ── What "data stopped" means ─────────────────────────────────────────────────


def test_the_gate_assertion_is_subject_relative_not_dataset_wide():
    """A 403 is not the only correct outcome, and demanding one was a real bug.

    Consent gates by **row filter**, per subject. One subject withdrawing removes
    that subject's rows and leaves everyone else's; a 403 happens only when
    nobody is left authorised. The first version demanded a 403 and **passed
    standalone** — in isolation this subject is the only consenter — then failed
    the moment it ran after `smoke`, which provisions a scoped wildcard for other
    parties. It was asserting a property of the dataset while claiming one about
    a person, and the fixture hid the difference.

    Pinned against the source because the failure is a fixture-dependent live
    run: cheap to reintroduce, expensive to notice.
    """
    import inspect

    from ds_e2e.flows.consent_withdrawal import ConsentWithdrawalFlow

    source = inspect.getsource(ConsentWithdrawalFlow.execute)
    assert "rows_after < rows_before" in source, (
        "the gate step no longer accepts a reduced row count — it is back to "
        "demanding a dataset-wide refusal"
    )


def test_started_is_not_a_stopped_state():
    """The assertion is worthless if the state it starts in also satisfies it."""
    assert "STARTED" not in STOPPED_TRANSFER_STATES
    assert "TERMINATED" in STOPPED_TRANSFER_STATES


def test_the_flow_is_registered_and_runs_after_smoke():
    """Order is load-bearing: `smoke` provisions the scoped wildcard consent this
    flow has to out-rank with an explicit opt-out (`D-15`)."""
    names = list(FLOW_REGISTRY)
    assert "consent-withdrawal" in names
    assert names.index("consent-withdrawal") > names.index("smoke")


def test_it_is_reachable_from_the_cli():
    """A registered flow absent from the enum cannot be run on its own — which is
    exactly how somebody would try to reproduce a failure."""
    from ds_e2e.cli import FlowName

    assert "consent-withdrawal" in {f.value for f in FlowName}


def test_os_environ_is_not_consulted_directly_by_the_flow():
    """Settings, not `os.getenv`. A second reader of one variable is how a flow
    ends up waiting on a value the platform is not using."""
    import inspect

    from ds_e2e.flows import consent_withdrawal

    source = inspect.getsource(consent_withdrawal)
    assert "os.environ" not in source and "getenv" not in source
    assert os is not None  # the import above is the thing being ruled out
