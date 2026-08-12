"""The compliance access log — rulebook `L-12`.

`GET /audit/log` and `/audit/log/summary` have always read a table nothing wrote:
`POST /audit/log` exists and no component in the platform calls it. Both surfaces
answered truthfully about an empty table, which is indistinguishable from a
dataspace in which nobody ever queried anything.

The event that already arrives *is* the query audit — the connector's PEP route
is `POST /internal/audit/query` and it emits `QueryExecuted` — so the log row is
derived from it. `POST /audit/log` stays for a data plane that reports directly.
"""
from __future__ import annotations

import pytest

QUERY_EVENT = {
    "event_type": "QueryExecuted",
    "event_id": "audit-q-1",
    "occurred_at": "2026-03-01T10:00:00Z",
    "data_product_id": "urn:dataset:meters",
    "provider_did": "did:web:provider.test",
    "consumer_did": "did:web:consumer.test",
    "agreement_id": "urn:uuid:agr-1",
    "transfer_id": "urn:uuid:tr-1",
    "row_count": 42,
    "authorized_subject_ids": ["did:example:alice", "did:example:bob"],
}


@pytest.mark.rule("L-12")
@pytest.mark.asyncio
async def test_a_query_event_writes_a_compliance_row(client):
    assert (await client.post("/prov/events", json=QUERY_EVENT)).status_code == 201

    entries = (await client.get("/audit/log")).json()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["consumer_id"] == "did:web:consumer.test"
    assert entry["dataset_id"] == "urn:dataset:meters"
    assert entry["agreement_id"] == "urn:uuid:agr-1"
    assert entry["transfer_id"] == "urn:uuid:tr-1"
    assert entry["rows_returned"] == 42
    assert entry["subject_ids"] == ["did:example:alice", "did:example:bob"]


@pytest.mark.rule("L-12")
@pytest.mark.asyncio
async def test_the_summary_counts_real_queries(client):
    await client.post("/prov/events", json=QUERY_EVENT)
    await client.post(
        "/prov/events",
        json=dict(QUERY_EVENT, event_id="audit-q-2", consumer_did="did:web:other.test"),
    )

    summary = (await client.get("/audit/log/summary?dataset_id=urn:dataset:meters")).json()
    assert summary["total_queries"] == 2
    assert summary["unique_consumers"] == 2
    assert summary["unique_subjects"] == 2


@pytest.mark.rule("L-12")
@pytest.mark.asyncio
async def test_subject_id_narrows_the_log(client):
    """Declared since the route was written and never applied — so "every query
    that touched this person's rows" returned the whole log."""
    await client.post("/prov/events", json=QUERY_EVENT)
    await client.post(
        "/prov/events",
        json=dict(
            QUERY_EVENT,
            event_id="audit-q-3",
            authorized_subject_ids=["did:example:carol"],
        ),
    )

    assert len((await client.get("/audit/log")).json()) == 2

    alice = (await client.get("/audit/log?subject_id=did:example:alice")).json()
    assert len(alice) == 1
    assert "did:example:alice" in alice[0]["subject_ids"]

    carol = (await client.get("/audit/log?subject_id=did:example:carol")).json()
    assert len(carol) == 1
    assert carol[0]["subject_ids"] == ["did:example:carol"]

    assert (await client.get("/audit/log?subject_id=did:example:nobody")).json() == []


@pytest.mark.asyncio
async def test_a_query_with_no_consumer_writes_no_row(client):
    """A compliance record that cannot name who queried is not one. Skipping is
    honest; a placeholder consumer would be a fabricated party in an audit log."""
    anonymous = {k: v for k, v in QUERY_EVENT.items() if k != "consumer_did"}
    anonymous["event_id"] = "audit-q-anon"
    assert (await client.post("/prov/events", json=anonymous)).status_code == 201

    assert (await client.get("/audit/log")).json() == []


@pytest.mark.asyncio
async def test_the_direct_write_route_still_works(client):
    entry = {
        "consumer_id": "did:web:external.test",
        "dataset_id": "urn:dataset:meters",
        "rows_returned": 3,
    }
    assert (await client.post("/audit/log", json=entry)).status_code == 201
    assert len((await client.get("/audit/log")).json()) == 1


@pytest.mark.asyncio
async def test_the_log_limit_is_bounded(client):
    assert (await client.get("/audit/log?limit=100000")).status_code == 422
    assert (await client.get("/audit/log?offset=-1")).status_code == 422
