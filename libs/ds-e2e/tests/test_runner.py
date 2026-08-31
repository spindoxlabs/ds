"""The runner's own contract: every flow gets its cleanup, whatever happened.

`BaseFlow.cleanup` had no caller — `E2E-10` recorded it as dead code, and it
stayed dead while `fail_closed.py` documented it as the net that restores a
stopped container. A net nothing holds is worse than no net, because the flow
that relies on it reads as safe.
"""

from __future__ import annotations

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY, BaseFlow
from ds_e2e.models import FlowResult
from ds_e2e.runner import run_flow


class _Recorder(BaseFlow):
    name = "recorder"
    description = "records whether cleanup ran"

    raises: BaseException | None = None

    def __init__(self, settings, http):
        super().__init__(settings, http)
        type(self).cleaned = False

    def execute(self) -> FlowResult:
        if type(self).raises is not None:
            raise type(self).raises
        result = FlowResult(flow_name=self.name)
        result.pass_step("ran", "")
        return result

    def cleanup(self) -> None:
        type(self).cleaned = True


@pytest.fixture
def registered(monkeypatch):
    def _register(cls):
        monkeypatch.setitem(FLOW_REGISTRY, cls.name, cls)
        return cls

    return _register


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def test_cleanup_runs_after_a_successful_flow(registered, settings):
    cls = registered(type("Ok", (_Recorder,), {"raises": None}))
    assert run_flow(cls.name, settings).passed
    assert cls.cleaned


def test_cleanup_runs_when_the_flow_raises(registered, settings):
    """The path that matters: an exception mid-outage must still restore the PDP."""
    cls = registered(type("Boom", (_Recorder,), {"raises": RuntimeError("mid-outage")}))
    with pytest.raises(RuntimeError):
        run_flow(cls.name, settings)
    assert cls.cleaned


def test_cleanup_runs_on_keyboard_interrupt(registered, settings):
    """Ctrl-C during a two-minute flow is how a stopped container gets left down."""
    cls = registered(type("Interrupted", (_Recorder,), {"raises": KeyboardInterrupt()}))
    with pytest.raises(KeyboardInterrupt):
        run_flow(cls.name, settings)
    assert cls.cleaned


def test_a_failing_cleanup_does_not_replace_the_flows_verdict(registered, settings):
    """`E2E-14`, one layer out: a teardown error must not become the result.

    A cleanup that raises would otherwise turn a flow that recorded real steps
    into a traceback with no results at all — the failure mode where one broken
    thing erases the evidence about everything else."""

    class Untidy(_Recorder):
        name = "untidy"

        def cleanup(self) -> None:
            raise RuntimeError("teardown failed")

    registered(Untidy)
    result = run_flow("untidy", settings)
    assert result.passed
    assert [s.name for s in result.steps] == ["ran"]


def test_cleanup_is_not_attempted_when_the_flow_cannot_be_constructed(
    registered, settings, monkeypatch
):
    """No instance, nothing to clean — and no `AttributeError` in the `finally`."""

    class Unbuildable(_Recorder):
        name = "unbuildable"

        def __init__(self, settings, http):
            raise RuntimeError("bad settings")

    registered(Unbuildable)
    with pytest.raises(RuntimeError, match="bad settings"):
        run_flow("unbuildable", settings)
