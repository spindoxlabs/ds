"""`POST /query` in dataspace mode — what the PEP does with ds's decision.

Every test here stubs `_authorize`, because the decision is ds's and this suite
is about enforcement, not about how the decision was reached. What it must never
stub is the reading of that decision: that is the seam the 500 lived on.
"""

from __future__ import annotations

import pytest
from ds.governance import ALLOW, DENY, DIRECT_USER_MATCH, DataplaneDecision
from fastapi.testclient import TestClient

from dataset_api_mock import main

GATED = "datasets.silver.meters_15m"
SUBJECT = "did:web:users.dataspaces.localhost:data-subject"
OTHER = "did:web:users.dataspaces.localhost:subject-002"

HEADERS = {
    "Authorization": "Bearer irrelevant-the-verifier-is-stubbed",
    "Edc-Contract-Agreement-Id": "agr-1",
    "Edc-Purpose": "FlexibilityResearch",
}


def _decision(verdict: dict) -> DataplaneDecision:
    return DataplaneDecision.model_validate(
        {
            "decision": verdict["decision"],
            "reason": verdict.get("reason"),
            "agreement_id": "agr-1",
            "transfer_id": None,
            "purpose": ["FlexibilityResearch"],
            "datasets": [verdict],
            "cache": {"ttl_seconds": 30},
        }
    )


@pytest.fixture
def client(monkeypatch):
    async def consumer(_bearer):
        return "did:web:consumer.dataspaces.localhost"

    async def audited(**_kwargs):
        return None

    monkeypatch.setattr(main, "_verified_consumer", consumer)
    monkeypatch.setattr(main, "_audit_query", audited)
    return TestClient(main.app)


def _answers(monkeypatch, decision: DataplaneDecision):
    async def authorize(**_kwargs):
        return decision

    monkeypatch.setattr(main, "_authorize", authorize)


def _query(client) -> object:
    return client.post(
        "/query",
        json={"sql": f"SELECT * FROM {GATED}", "limit": 100},
        headers=HEADERS,
    )


def test_an_allow_with_a_filter_serves_only_the_consenting_rows(client, monkeypatch):
    _answers(
        monkeypatch,
        _decision(
            {
                "dataset_id": GATED,
                "decision": ALLOW,
                "row_filter": {
                    "handler": DIRECT_USER_MATCH,
                    "args": {"column": "sub"},
                    "principals": [SUBJECT],
                },
            }
        ),
    )
    response = _query(client)
    assert response.status_code == 200
    served = {row["sub"] for row in response.json()["items"]}
    assert served == {SUBJECT}
    assert OTHER not in served


def test_an_allow_with_a_filter_is_not_a_500(client, monkeypatch):
    """The regression itself.

    `row_filter["column"]` against a filter shaped `{handler, args, principals}`
    raised `KeyError` — a 500 out of the one code path whose job is to narrow.
    """
    _answers(
        monkeypatch,
        _decision(
            {
                "dataset_id": GATED,
                "decision": ALLOW,
                "row_filter": {
                    "handler": DIRECT_USER_MATCH,
                    "args": {"column": "sub"},
                    "principals": [SUBJECT],
                },
            }
        ),
    )
    assert _query(client).status_code == 200


def test_a_handler_this_plane_cannot_run_serves_nothing(client, monkeypatch):
    _answers(
        monkeypatch,
        _decision(
            {
                "dataset_id": GATED,
                "decision": ALLOW,
                "row_filter": {
                    "handler": "rec_registry",
                    "args": {"column": "device_id"},
                    "principals": ["member-1"],
                },
            }
        ),
    )
    assert _query(client).status_code == 403


def test_an_allowing_envelope_over_a_denying_verdict_serves_nothing(client, monkeypatch):
    """A join's envelope is the strictest of its verdicts, but the two are
    separate fields and only the verdict speaks for *this* dataset."""
    decision = _decision({"dataset_id": GATED, "decision": DENY, "reason": "no_consent"})
    decision.decision = ALLOW
    _answers(monkeypatch, decision)
    response = _query(client)
    assert response.status_code == 403
    assert "no_consent" in response.json()["detail"]


def test_a_dataset_the_decision_never_mentions_serves_nothing(client, monkeypatch):
    """Silence about a dataset is not consent to serve it."""
    _answers(
        monkeypatch,
        _decision({"dataset_id": "datasets.gold.om_weather_features", "decision": ALLOW}),
    )
    response = _query(client)
    assert response.status_code == 403
    assert "dataset_undecided" in response.json()["detail"]


def test_a_deny_serves_nothing_and_relays_the_gate(client, monkeypatch):
    _answers(
        monkeypatch,
        _decision({"dataset_id": GATED, "decision": DENY, "reason": "purpose_required"}),
    )
    response = _query(client)
    assert response.status_code == 403
    assert "purpose_required" in response.json()["detail"]
