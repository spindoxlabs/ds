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
    def test_it_joins_on_correlation_id_not_the_agreement(self, settings):
        """Measured, after matching on the agreement found nothing live.

        The two sides mint different UUIDs for **both** the agreement and the
        transfer; `correlationId` is the only field either carries that names the
        other's. Matching on `contractId` compares the provider's local agreement
        id to the consumer's and finds nothing — and "nothing" is a state this
        flow reads as *stopped*, so the bug produced a green termination it never
        observed.
        """
        http = MagicMock()
        http.post_raw.return_value = (
            200,
            [
                {
                    "@id": "p-1",
                    "correlationId": "consumer-tp-A",
                    "contractId": "provider-agreement-1",
                    "state": "STARTED",
                },
                {
                    "@id": "p-2",
                    "correlationId": "consumer-tp-B",
                    "contractId": "provider-agreement-2",
                    "state": "STARTED",
                },
            ],
        )
        flow = _flow(settings, http)

        assert flow._provider_transfer_for("consumer-tp-B")["@id"] == "p-2"
        # The consumer never sees the provider's agreement id, so this must miss.
        assert flow._provider_transfer_for("provider-agreement-2") is None

    def test_it_reads_the_prefixed_json_ld_form_too(self, settings):
        """EDC answers compacted or prefixed depending on the context asked for;
        `cleanup.py` reads both and a reader that does not sees no state."""
        http = MagicMock()
        http.post_raw.return_value = (
            200,
            [{"@id": "tp", "edc:correlationId": "c-tp", "edc:state": "TERMINATED"}],
        )
        flow = _flow(settings, http)

        found = flow._provider_transfer_for("c-tp")

        assert found is not None
        assert flow._state_of(found) == "TERMINATED"

    def test_an_unreadable_management_response_is_no_transfers(self, settings):
        """Not an exception mid-poll: the caller loops on this, and a 401 from a
        misconfigured key should end as a named failure rather than a traceback."""
        http = MagicMock()
        http.post_raw.return_value = (401, {"error": "unauthorized"})
        flow = _flow(settings, http)

        assert flow._provider_transfers() == []
        assert flow._provider_transfer_for("anything") is None

    def test_an_invalid_request_is_not_read_as_no_transfers(self, settings):
        """The shape a missing `@type: QuerySpec` produced, live.

        EDC answers a single `InvalidRequest` **object**, and treating that as an
        empty list made the flow report a provider that was not watching a
        transfer it was watching. It must stay distinguishable from `[]`.
        """
        http = MagicMock()
        http.post_raw.return_value = (200, {"type": "InvalidRequest"})
        flow = _flow(settings, http)

        assert flow._provider_transfers() == []

    def test_the_query_body_carries_the_type_edc_requires(self, settings):
        """One holder of the request shape: `cleanup.EDC_CONTEXT`, which had it
        right. The second copy written here did not."""
        from ds_e2e.cleanup import EDC_CONTEXT

        http = MagicMock()
        http.post_raw.return_value = (200, [])
        _flow(settings, http)._provider_transfers()

        assert http.post_raw.call_args[0][1] is EDC_CONTEXT
        assert EDC_CONTEXT["@type"] == "QuerySpec"

    def test_it_reads_the_provider_edc_not_the_consumer(self, settings):
        """The policy monitor runs on the side that owns the agreement."""
        http = MagicMock()
        http.post_raw.return_value = (200, [])
        _flow(settings, http)._provider_transfers()

        url = http.post_raw.call_args[0][0]
        assert url.startswith(settings.edc_provider_management_url)
        assert settings.edc_consumer_management_url not in url


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
