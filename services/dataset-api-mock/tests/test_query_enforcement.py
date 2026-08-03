"""`POST /query` in dataspace mode — what the PEP does with ds's decision.

Every test here stubs `_authorize`, because the decision is ds's and this suite
is about enforcement, not about how the decision was reached. What it must never
stub is the reading of that decision: that is the seam the 500 lived on.
"""

from __future__ import annotations

import pytest
from ds.governance import ALLOW, DENY, DataplaneDecision
from fastapi.testclient import TestClient

from dataset_api_mock import main
from dataset_api_mock.main import REC_REGISTRY

GATED = "datasets.silver.meters_15m"
# ds names a consenting person by the identifier the *receiving* system keys on —
# a Keycloak username — never by DID. The devices behind them are this plane's to
# resolve, which is why the principal and the column values differ.
SUBJECT = "subject@example.test"
SUBJECT_DEVICE = "ds-e2e-METER-0001"
OTHER_DEVICE = "ds-e2e-METER-0002"
UNOWNED_DEVICE = "ds-e2e-METER-9999"

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


def _rec_allow(principals: list[str]) -> dict:
    """An allow shaped exactly as `governance.yaml` declares this dataset.

    Not `direct_user_match` on a column the fixture invented for itself: the
    whole defect this replaces was that the mock's vocabulary and governance's
    were different, so a test written in the mock's own terms passed while the
    dataset was unserveable in the stack.
    """
    return {
        "dataset_id": GATED,
        "decision": ALLOW,
        "row_filter": {
            "handler": REC_REGISTRY,
            "args": {"column": "device_id"},
            "principals": principals,
        },
    }


def test_an_allow_with_a_filter_serves_only_the_consenting_rows(client, monkeypatch):
    _answers(monkeypatch, _decision(_rec_allow([SUBJECT])))
    response = _query(client)
    assert response.status_code == 200
    served = {row["device_id"] for row in response.json()["items"]}
    assert served == {SUBJECT_DEVICE}
    assert OTHER_DEVICE not in served
    assert UNOWNED_DEVICE not in served


def test_an_allow_with_a_filter_is_not_a_500(client, monkeypatch):
    """The regression itself.

    `row_filter["column"]` against a filter shaped `{handler, args, principals}`
    raised `KeyError` — a 500 out of the one code path whose job is to narrow.
    """
    _answers(monkeypatch, _decision(_rec_allow([SUBJECT])))
    assert _query(client).status_code == 200


def test_the_platforms_one_consent_gated_dataset_is_serveable(client, monkeypatch):
    """It was not, and nothing failed to say so.

    The fixture keyed rows by subject DID in a column `sub`, while
    `governance.yaml` declares `rec_registry` on `device_id` and ds sends
    usernames. Every one of those disagreed with the next, so an *allow* narrowed
    to nothing and looked exactly like a subject who had consented to nothing.
    """
    _answers(monkeypatch, _decision(_rec_allow([SUBJECT])))
    assert _query(client).json()["count"] == 2


def test_a_handler_this_plane_cannot_run_serves_nothing(client, monkeypatch):
    _answers(
        monkeypatch,
        _decision(
            {
                "dataset_id": GATED,
                "decision": ALLOW,
                "row_filter": {
                    "handler": "postgres_row_security",
                    "args": {"column": "device_id"},
                    "principals": [SUBJECT],
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
