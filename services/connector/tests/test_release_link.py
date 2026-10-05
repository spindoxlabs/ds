"""The release link: an allow names what it served, and the read report carries it.

ADR-0027. `POST /internal/dataplane/authorize` returns a `decision_ref` on an
allow — a digest of the agreement and the keys served — and the data plane
echoes it, with the agreement, into `POST /internal/audit/query`, which forwards
both to `QueryExecuted`. An auditor holding the holder's key ledger recomputes
it without opening a key.
"""

from __future__ import annotations

import hashlib

import pytest
from ds.governance import DataplaneDecision
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.sealed import blind_index
from connector.services.consent_service import set_subject_data_sharing
from tests import make_headers
from tests.test_dataplane_authorize import (
    CONSUMER,
    GATED,
    SUBJECT,
    _agreement,
    _authorize,
    _resolvable_subjects,  # noqa: F401 — autouse fixture, re-exported here
)

INTERNAL = make_headers(scope="connector.internal")
KEYS = ["pod:EX000E00000002", "pod:EX000E00000001"]


async def _consent_with_keys(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await set_subject_data_sharing(
            session,
            subject_id=SUBJECT,
            dataset_id=GATED,
            consumer_id=CONSUMER,
            enabled=True,
            purpose=["FlexibilityResearch"],
            keys=sorted(KEYS),
        )


@pytest.mark.rule("D-12b", "L-2")
@pytest.mark.asyncio
async def test_an_allow_carries_the_documented_decision_ref(engine, client):
    await _agreement(engine, "agr-1", GATED)
    await _consent_with_keys(engine)
    r = await _authorize(client)
    assert r.status_code == 200, r.text
    decision = DataplaneDecision.model_validate(r.json())
    assert decision.allowed
    assert sorted(decision.datasets[0].row_filter.keys) == sorted(KEYS)
    indexes = sorted(blind_index(k) for k in KEYS)
    expected = hashlib.sha256(("agr-1\n" + "\n".join(indexes)).encode()).hexdigest()
    assert decision.decision_ref == expected


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_an_allow_with_no_keys_still_names_its_agreement(engine, client):
    await _agreement(engine, "agr-1", GATED)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await set_subject_data_sharing(
            session,
            subject_id=SUBJECT,
            dataset_id=GATED,
            consumer_id=CONSUMER,
            enabled=True,
            purpose=["FlexibilityResearch"],
        )
    body = (await _authorize(client)).json()
    assert body["decision"] == "allow"
    assert body["decision_ref"] == hashlib.sha256(b"agr-1\n").hexdigest()


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_deny_releases_nothing_and_names_no_decision(client):
    body = (await _authorize(client, agreement_id="nope")).json()
    assert body["decision"] == "deny"
    assert body["decision_ref"] is None


class _Prov:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def query_executed(self, **kw):
        self.calls.append(kw)


@pytest.mark.rule("D-12b", "L-2")
@pytest.mark.asyncio
async def test_the_read_report_forwards_the_link_and_the_agreement(client):
    fake = _Prov()
    client._transport.app.state.prov = fake
    ref = "a" * 64
    r = await client.post(
        "/internal/audit/query",
        headers=INTERNAL,
        json={
            "dataset_id": GATED,
            "consumer_id": CONSUMER,
            "agreement_id": "agr-1",
            "row_count": 3,
            "decision_ref": ref,
        },
    )
    assert r.status_code == 202, r.text
    [call] = fake.calls
    assert (call["decision_ref"], call["agreement_id"]) == (ref, "agr-1")


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_link_that_is_not_a_digest_is_refused(client):
    client._transport.app.state.prov = _Prov()
    r = await client.post(
        "/internal/audit/query",
        headers=INTERNAL,
        json={"dataset_id": GATED, "decision_ref": "pending"},
    )
    assert r.status_code == 422, r.text
