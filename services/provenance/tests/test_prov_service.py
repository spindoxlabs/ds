"""`upsert_node` — the two things it got wrong about a node it had seen before.

Both are rulebook `L-8`: a node's type and what is known about it belong to the
node, not to the first event that happened to mention it.
"""
from __future__ import annotations

import pytest

from provenance.db.models import ProvNodeORM
from provenance.services.prov_service import upsert_node


@pytest.mark.asyncio
async def test_node_type_follows_the_latest_statement(db_session):
    """The first event to mention an IRI used to fix its type permanently.

    A DID first seen as the `source_ref` of a disclosure stayed an Entity even
    once a later event named it as the agent it is — and every edge touching it
    then published the wrong endpoint type.
    """
    await upsert_node(db_session, "did:web:provider.test", "Entity", label="misfiled")
    await db_session.flush()

    await upsert_node(db_session, "did:web:provider.test", "Agent", label="provider")
    await db_session.flush()

    node = await db_session.get(ProvNodeORM, (await _one(db_session)).id)
    assert node.node_type == "Agent"


@pytest.mark.asyncio
async def test_external_meta_accumulates_rather_than_replacing(db_session):
    """`NegotiationStarted` records the offer, `NegotiationFinalized` the
    agreement, both on the same activity node. Replacing the block dropped the
    offer id the moment the agreement arrived."""
    await upsert_node(
        db_session, "urn:activity:negotiation:n1", "Activity",
        external_meta={"negotiationId": "n1", "offerId": "offer-7"},
    )
    await db_session.flush()

    await upsert_node(
        db_session, "urn:activity:negotiation:n1", "Activity",
        external_meta={"negotiationId": "n1", "agreementId": "agr-3"},
    )
    await db_session.flush()

    node = await _one(db_session)
    assert node.external_meta == {
        "negotiationId": "n1",
        "offerId": "offer-7",
        "agreementId": "agr-3",
    }


@pytest.mark.asyncio
async def test_an_unknown_value_does_not_erase_a_known_one(db_session):
    """`None` on the incoming side means *this event does not know*, never
    *forget what you knew* — an optional field absent from a later event must not
    blank a value an earlier one supplied."""
    await upsert_node(
        db_session, "urn:activity:negotiation:n2", "Activity",
        external_meta={"offerId": "offer-9"},
    )
    await db_session.flush()

    await upsert_node(
        db_session, "urn:activity:negotiation:n2", "Activity",
        external_meta={"offerId": None, "reason": "terminated"},
    )
    await db_session.flush()

    node = await _one(db_session)
    assert node.external_meta["offerId"] == "offer-9"
    assert node.external_meta["reason"] == "terminated"


@pytest.mark.asyncio
async def test_the_negotiation_pair_keeps_both_ids_end_to_end(client):
    """The same defect through the ingest route, which is where it bit."""
    started = {
        "event_type": "NegotiationStarted",
        "event_id": "neg-started-1",
        "occurred_at": "2026-01-01T10:00:00Z",
        "negotiation_id": "n-100",
        "data_product_id": "urn:dataset:meters",
        "provider_did": "did:web:provider.test",
        "consumer_did": "did:web:consumer.test",
        "offer_id": "offer-100",
    }
    finalized = {
        "event_type": "NegotiationFinalized",
        "event_id": "neg-finalized-1",
        "occurred_at": "2026-01-01T10:05:00Z",
        "negotiation_id": "n-100",
        "agreement_id": "agr-100",
        "data_product_id": "urn:dataset:meters",
        "provider_did": "did:web:provider.test",
        "consumer_did": "did:web:consumer.test",
    }
    assert (await client.post("/prov/events", json=started)).status_code == 201
    assert (await client.post("/prov/events", json=finalized)).status_code == 201

    import urllib.parse
    iri = urllib.parse.quote("urn:activity:negotiation:n-100", safe="")
    body = (await client.get(f"/prov/activities/{iri}")).json()
    node = body["@graph"][0]
    assert node["offerId"] == "offer-100"
    assert node["agreementId"] == "agr-100"


async def _one(session) -> ProvNodeORM:
    from sqlalchemy import select
    result = await session.execute(select(ProvNodeORM).order_by(ProvNodeORM.created_at.desc()))
    return result.scalars().first()
