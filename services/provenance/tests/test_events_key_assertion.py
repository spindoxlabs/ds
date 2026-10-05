"""The R4 references on the chain: keys digest, assertion, release link, suspension.

ADR-0027. A holder's connector puts on the record what a collector asserted about
the keys it registered (inside ``legal_basis``), a digest of those keys
(``keys_digest``) and of the assertion (``assertion_ref``); the data plane echoes
a ``decision_ref`` into ``QueryExecuted``; and a holder's suspension of a key is
its own event. All of them are hashes — never a key — and all of them are
covered by the chain (`L-17`).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from provenance.db.models import DomainEventORM

SUBJECT = "did:web:rec.example.org:users:ex-00001"

ASSERTION = {
    "terms": "rec-pod-assertion/1",
    "terms_sha256": "1" * 64,
    "method": "uploaded-document",
    "verification_ref": "00000000-0000-4000-8000-000000000001",
    "verified_by": "2" * 64,
    "verified_at": "2026-02-01T09:00:00+00:00",
    "evidence": [{"kind": "utility_bill", "sha256": "3" * 64}],
}

GRANTED = {
    "event_type": "ConsentGranted",
    "event_id": "r4-granted-001",
    "occurred_at": "2026-02-01T10:00:00Z",
    "subject_id": SUBJECT,
    "dataset_id": "datasets.silver.grid_meters",
    "consumer_did": "*",
    "offer_id": "grid-meter-release",
    "purpose": ["GridMonitoring"],
    "legal_basis": {"consent_text_version": "1.0", "key_assertion": ASSERTION},
    "collector": "did:web:rec.example.org",
    "keys_supplied": True,
    "keys_digest": "a" * 64,
    "assertion_ref": "b" * 64,
}

QUERY = {
    "event_type": "QueryExecuted",
    "event_id": "r4-query-001",
    "occurred_at": "2026-02-02T10:00:00Z",
    "data_product_id": "datasets.silver.grid_meters",
    "provider_did": "did:web:dso.example.org",
    "consumer_did": "did:web:consumer.example.org",
    "agreement_id": "agreement-1",
    "decision_ref": "c" * 64,
}

SUSPENDED = {
    "event_type": "KeySuspension",
    "action": "suspended",
    "event_id": "r4-suspended-001",
    "occurred_at": "2026-02-03T10:00:00Z",
    "provider_did": "did:web:dso.example.org",
    "subject_id": SUBJECT,
    "keys_digest": "d" * 64,
    "reason": "holder_change",
    "grants_affected": 2,
}

LIFTED = {
    "event_type": "KeySuspension",
    "action": "lifted",
    "event_id": "r4-lifted-001",
    "occurred_at": "2026-02-04T10:00:00Z",
    "provider_did": "did:web:dso.example.org",
    "subject_id": SUBJECT,
    "keys_digest": "d" * 64,
    "assertion_ref": "e" * 64,
    "collector": "did:web:rec.example.org",
}


async def _stored(engine, event_id: str) -> dict:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        row = (
            await session.execute(
                select(DomainEventORM).where(DomainEventORM.event_id == event_id)
            )
        ).scalar_one()
        return row.payload


@pytest.mark.rule("D-12b", "L-17")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [GRANTED, QUERY, SUSPENDED, LIFTED],
    ids=["granted", "query", "suspended", "lifted"],
)
async def test_the_r4_references_are_recorded_and_chained(client, event):
    r = await client.post("/prov/events", json=event)
    assert r.status_code == 201, r.text
    assert r.json()["prov_node_id"] is not None
    verify = await client.get("/prov/chain/verify")
    assert verify.status_code == 200, verify.text
    assert verify.json()["ok"] is True


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_granted_event_keeps_the_assertion_and_both_digests(client, engine):
    await client.post("/prov/events", json=GRANTED)
    payload = await _stored(engine, "r4-granted-001")
    assert payload["keys_digest"] == "a" * 64
    assert payload["assertion_ref"] == "b" * 64
    assert payload["legal_basis"]["key_assertion"] == ASSERTION


@pytest.mark.rule("D-12b", "L-2")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "field"),
    [
        (GRANTED, "keys_digest"),
        (GRANTED, "assertion_ref"),
        (QUERY, "decision_ref"),
        (SUSPENDED, "keys_digest"),
    ],
)
async def test_a_reference_that_is_not_a_digest_is_refused(client, event, field):
    """A value that cannot be a digest proves nothing; the schema says so."""
    r = await client.post(
        "/prov/events", json={**event, "event_id": f"bad-{field}", field: "pending"}
    )
    assert r.status_code == 422, r.text


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_suspension_names_only_holder_change(client):
    r = await client.post(
        "/prov/events", json={**SUSPENDED, "event_id": "bad", "reason": "because"}
    )
    assert r.status_code == 422, r.text


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_lift_names_the_assertion_that_lifted_it(client):
    lift = {k: v for k, v in LIFTED.items() if k != "assertion_ref"}
    r = await client.post("/prov/events", json={**lift, "event_id": "bad-lift"})
    assert r.status_code == 422, r.text
