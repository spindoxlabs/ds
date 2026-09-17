"""`onboarding-seam` reads the audience the way `D-14` bounds it (#37).

After `229193b`, `GET /consent/admin/shares` answers the way the data plane
does: a wildcard grant reaches the offer's controller and the processors its
`admitted_by` admits, and nobody else. The flow read the audience for the dev
consumer, which is a processor but not a member of the controller, and expected
the subject. These pin the corrected expectation without a stack.
"""

from __future__ import annotations

import urllib.parse
from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY
from ds_e2e.flows.onboarding_seam import OnboardingSeamFlow
from ds_e2e.models import FlowResult

OFFER = {"id": "household-energy-flexibility", "dataset_count": 1}


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def _audience(settings: E2ESettings, subjects: list[str]) -> dict:
    return {
        "offer_id": OFFER["id"],
        "purpose": [settings.consented_purpose],
        "datasets": [{"dataset_id": "datasets.silver.meters", "subject_ids": subjects}],
    }


def _consumer_of(call) -> str | None:
    url = call.args[1]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    return (query.get("consumer_id") or [None])[0]


def test_the_flow_names_d14():
    assert "D-14" in FLOW_REGISTRY["onboarding-seam"].rules


def test_the_audience_is_read_for_the_offers_controller(settings):
    http = MagicMock()
    http.raw.side_effect = [
        (200, _audience(settings, [settings.data_subject_id])),
        (422, {"detail": "consumer_id required"}),
    ]
    flow, result = OnboardingSeamFlow(settings, http), FlowResult(flow_name="t")

    assert flow._read_the_audience(result, {}, OFFER)

    assert _consumer_of(http.raw.call_args_list[0]) == settings.provider_did
    assert [s.status for s in result.steps] == ["PASS"]


def test_an_outsider_that_sees_no_wildcard_subject_passes(settings):
    http = MagicMock()
    http.raw.return_value = (200, _audience(settings, []))
    flow, result = OnboardingSeamFlow(settings, http), FlowResult(flow_name="t")

    assert flow._check_the_audience_is_bounded(result, {}, OFFER)

    assert _consumer_of(http.raw.call_args) == settings.consumer_did
    assert [s.status for s in result.steps] == ["PASS"]


def test_an_outsider_that_sees_the_wildcard_subject_fails(settings):
    """The #37 defect, as the flow now detects it live."""
    http = MagicMock()
    http.raw.return_value = (200, _audience(settings, [settings.data_subject_id]))
    flow, result = OnboardingSeamFlow(settings, http), FlowResult(flow_name="t")

    assert not flow._check_the_audience_is_bounded(result, {}, OFFER)

    assert [s.status for s in result.steps] == ["FAIL"]
    assert "outside the offer's circle" in result.steps[0].detail


def test_a_refused_outsider_read_fails(settings):
    http = MagicMock()
    http.raw.return_value = (403, {"detail": "forbidden"})
    flow, result = OnboardingSeamFlow(settings, http), FlowResult(flow_name="t")

    assert not flow._check_the_audience_is_bounded(result, {}, OFFER)
    assert [s.status for s in result.steps] == ["FAIL"]


def test_prior_decisions_are_cleared_for_both_parties(settings, monkeypatch):
    """The outsider's absence must come from `D-14`, not from a left-over opt-out."""
    from ds_e2e.flows import onboarding_seam

    executed = []
    cursor = MagicMock(rowcount=0)
    cursor.execute.side_effect = lambda sql, params: executed.append(params)
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    connect = MagicMock()
    connect.return_value.__enter__.return_value = conn
    monkeypatch.setattr(onboarding_seam.psycopg, "connect", connect)

    flow = OnboardingSeamFlow(settings, MagicMock())
    assert flow._clear_prior_decisions(FlowResult(flow_name="t"), OFFER)

    (params,) = executed
    assert set(params[1]) == {settings.provider_did, settings.consumer_did}
