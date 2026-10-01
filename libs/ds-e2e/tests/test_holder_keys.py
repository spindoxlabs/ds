"""The `holder-keys` flow's own reasoning (ADR-0022).

The live properties need a stack; pinned here is how the flow reads what it
observes — what counts as the served set, which refusals count, and what the
history must show.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from ds_e2e.cli import FlowName
from ds_e2e.config import E2ESettings
from ds_e2e.flows import FAST_FLOWS, FLOW_REGISTRY
from ds_e2e.flows.holder_keys import (
    POD_DUAL,
    POD_MEMBER,
    HolderKeysFlow,
)
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _flow(settings, raw) -> HolderKeysFlow:
    http = MagicMock(spec=HttpClient)
    http.raw.side_effect = raw
    http.bearer_headers.return_value = {"Authorization": "Bearer service"}
    http.user_headers.return_value = {"Authorization": "Bearer seat"}
    flow = HolderKeysFlow(settings, http)
    flow.collector = {"Authorization": "Bearer community"}
    flow.holder = {"Authorization": "Bearer holder"}
    flow.consumer = {"Authorization": "Bearer consumer"}
    flow.started = datetime.now(UTC)
    return flow


def _step(result: FlowResult, name: str):
    return next(s for s in result.steps if s.name == name)


def _keys(*pods: str, **extra) -> dict:
    return {
        "offer_id": "grid-meter-flexibility",
        "recipient": "consumer-org",
        "keys": [{"key_type": "pod", "value": p, "key": f"pod:{p}"} for p in pods],
        "next_cursor": None,
        **extra,
    }


def test_the_flow_is_registered_after_collector_holder():
    names = list(FLOW_REGISTRY)
    assert FLOW_REGISTRY["holder-keys"] is HolderKeysFlow
    assert names.index("collector-holder") < names.index("holder-keys")
    assert "holder-keys" in {f.value for f in FlowName}
    assert "holder-keys" not in FAST_FLOWS


@pytest.mark.rule("D-20")
def test_it_declares_the_rule_it_evidences():
    assert "D-20" in HolderKeysFlow.rules


def test_the_served_set_passes(settings):
    flow = _flow(settings, lambda *a, **k: (200, _keys(POD_MEMBER, POD_DUAL)))
    result = FlowResult(flow_name="holder-keys")
    flow._expect_keys(result, "keys", "offer", {POD_MEMBER, POD_DUAL})
    assert _step(result, "keys").status == "PASS"


@pytest.mark.parametrize(
    "answer",
    [
        (200, _keys(POD_MEMBER)),  # one missing
        (200, _keys(POD_MEMBER, POD_DUAL, "EX000E00000009")),  # the unadmitted one
        (200, _keys(POD_MEMBER, POD_DUAL, next_cursor="more")),  # truncated
        (403, {"detail": "nope"}),
    ],
    ids=["missing", "unadmitted-served", "truncated", "refused"],
)
def test_anything_but_the_served_set_fails(settings, answer):
    flow = _flow(settings, lambda *a, **k: answer)
    result = FlowResult(flow_name="holder-keys")
    flow._expect_keys(result, "keys", "offer", {POD_MEMBER, POD_DUAL})
    assert _step(result, "keys").status == "FAIL"


def test_a_member_s_did_in_the_answer_fails(settings):
    leak = _keys(POD_MEMBER, POD_DUAL, extra=settings.data_subject_id)
    flow = _flow(settings, lambda *a, **k: (200, leak))
    result = FlowResult(flow_name="holder-keys")
    flow._expect_keys(result, "keys", "offer", {POD_MEMBER, POD_DUAL})
    assert _step(result, "keys").status == "FAIL"


MISSING = (
    "Missing required permission: connector.consent.holder.read or connector.admin"
)


def _refusals(**override):
    answers = {
        "community": (
            403,
            {"detail": "a collector reads … GET /consent/admin/decisions"},
        ),
        "consumer": (
            403,
            {"detail": "a collector reads … GET /consent/admin/decisions"},
        ),
        "service": (
            403,
            {"detail": MISSING},
        ),
        "seat": (
            403,
            {"detail": MISSING},
        ),
    }
    answers.update(override)
    by_token = {
        "Bearer community": "community",
        "Bearer consumer": "consumer",
        "Bearer service": "service",
        "Bearer seat": "seat",
    }

    def raw(method, url, body=None, headers=None, **_):
        return answers[by_token[headers["Authorization"]]]

    return raw


def test_the_refusals_pass_only_with_their_own_causes(settings):
    flow = _flow(settings, _refusals())
    result = FlowResult(flow_name="holder-keys")
    flow._check_refusals(result)
    assert _step(result, "refused readers").status == "PASS"


@pytest.mark.parametrize(
    "override",
    [
        {"community": (200, _keys(POD_MEMBER))},
        {"consumer": (403, {"detail": "Missing required permission"})},
        {"seat": (200, _keys())},
    ],
    ids=["collector-reads", "wrong-cause", "seat-reads"],
)
def test_a_refusal_for_another_reason_fails(settings, override):
    flow = _flow(settings, _refusals(**override))
    result = FlowResult(flow_name="holder-keys")
    flow._check_refusals(result)
    assert _step(result, "refused readers").status == "FAIL"


def _history(*pairs):
    events = [{"key": f"pod:{POD_MEMBER}", "event": e, "cause": c} for e, c in pairs]
    return lambda *a, **k: (200, {"events": events, "next_cursor": None})


def test_the_history_must_end_with_the_grant_then_the_withdrawal(settings):
    ok = _flow(
        settings,
        _history(
            ("removed", "withdrawal"),  # an earlier run's reset
            ("added", "grant"),
            ("removed", "withdrawal"),
        ),
    )
    result = FlowResult(flow_name="holder-keys")
    ok._check_history(result)
    assert _step(result, "the history says when").status == "PASS"

    wrong = _flow(settings, _history(("removed", "withdrawal"), ("added", "grant")))
    result = FlowResult(flow_name="holder-keys")
    wrong._check_history(result)
    assert _step(result, "the history says when").status == "FAIL"
