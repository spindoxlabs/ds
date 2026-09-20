"""Tests for domain event ingest and PROV-O materialisation."""

import urllib.parse

import pytest


CATALOGUE_EVENT = {
    "event_type": "CataloguePublished",
    "event_id": "test-cat-001",
    "occurred_at": "2026-01-01T10:00:00Z",
    "data_product_id": "https://rec.dataspaces.localhost/datasets/meters_15m",
    "provider_did": "did:web:rec.dataspaces.localhost",
    "title": "Meter Readings 15m",
}

WITHDRAWAL_EVENT = {
    "event_type": "CatalogueWithdrawn",
    "event_id": "test-cat-withdraw-001",
    "occurred_at": "2026-01-04T10:00:00Z",
    "data_product_id": CATALOGUE_EVENT["data_product_id"],
    "provider_did": "did:web:rec.dataspaces.localhost",
    "reason": "undeclared",
}

WITHDRAWAL_ACTIVITY = (
    f"urn:activity:catalogue-withdrawal:{CATALOGUE_EVENT['data_product_id']}"
)

CONTRACT_EVENT = {
    "event_type": "ContractAgreementSigned",
    "event_id": "test-contract-001",
    "occurred_at": "2026-01-02T10:00:00Z",
    "agreement_id": "urn:uuid:agreement-001",
    "data_product_id": "https://rec.dataspaces.localhost/datasets/meters_15m",
    "provider_did": "did:web:rec.dataspaces.localhost",
    "consumer_did": "did:web:third-party.dataspaces.localhost",
}

TRANSFER_EVENT = {
    "event_type": "DataTransferCompleted",
    "event_id": "test-transfer-001",
    "occurred_at": "2026-01-03T10:00:00Z",
    "transfer_id": "urn:uuid:transfer-001",
    "agreement_id": "urn:uuid:agreement-001",
    "data_product_id": "https://rec.dataspaces.localhost/datasets/meters_15m",
    "provider_did": "did:web:rec.dataspaces.localhost",
    "consumer_did": "did:web:third-party.dataspaces.localhost",
    "bytes_transferred": 4096,
}


@pytest.mark.asyncio
async def test_ingest_catalogue_published(client):
    response = await client.post("/prov/events", json=CATALOGUE_EVENT)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    assert body["event_id"] == CATALOGUE_EVENT["event_id"]
    assert body["prov_node_id"] is not None


@pytest.mark.rule("L-4")
@pytest.mark.asyncio
async def test_ingest_duplicate_is_idempotent(client):
    r1 = await client.post("/prov/events", json=CATALOGUE_EVENT)
    assert r1.status_code == 201
    r2 = await client.post("/prov/events", json=CATALOGUE_EVENT)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


@pytest.mark.rule("L-5")
@pytest.mark.asyncio
async def test_catalogue_materialises_entity_and_activity(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)

    entities = await client.get("/prov/entities")
    entity_ids = [n["@id"] for n in entities.json()["@graph"]]
    assert CATALOGUE_EVENT["data_product_id"] in entity_ids

    activities = await client.get("/prov/activities")
    # CatalogPublication activity should exist
    activity_labels = [n.get("prov:label", "") for n in activities.json()["@graph"]]
    assert any("Catalog" in lbl or "Publication" in lbl for lbl in activity_labels)


@pytest.mark.rule("L-1", "L-15")
@pytest.mark.asyncio
async def test_a_withdrawal_invalidates_the_dataset_the_publication_generated(client):
    """`ADR-0017`'s owed counterpart: going off offer is now in the graph.

    A dataset removed from governance was taken off offer in EDC and recorded
    nowhere, so the last thing provenance said about it was that it had been
    published — not an incomplete record but a wrong one.

    Three things are asserted, and the middle one is the decision:

    1. the event is accepted and materialises a node;
    2. the edge is `prov:wasInvalidatedBy` **from the dataset to the
       withdrawal** — an invalidation on the entity's own record, not another
       generation and not the Activity→Entity direction, which would be equally
       valid PROV-O and would hide the fact from anything walking the dataset;
    3. it is the **same entity node** the publication generated — both events
       name the EDC asset id, so a withdrawal cannot invent a second dataset.
    """
    await client.post("/prov/events", json=CATALOGUE_EVENT)

    response = await client.post("/prov/events", json=WITHDRAWAL_EVENT)
    assert response.status_code == 201, response.text
    assert response.json()["prov_node_id"] is not None

    iri = urllib.parse.quote(str(CATALOGUE_EVENT["data_product_id"]), safe="")
    graph = (
        await client.get(f"/prov/lineage/{iri}?direction=both&max_depth=3")
    ).json()["@graph"]

    edges = [item for item in graph if "ds:source" in item]
    invalidations = [e for e in edges if e["@type"] == "prov:wasInvalidatedBy"]
    assert len(invalidations) == 1, edges
    assert invalidations[0]["ds:source"] == CATALOGUE_EVENT["data_product_id"]
    assert invalidations[0]["ds:target"] == WITHDRAWAL_ACTIVITY

    # The publication's own edge is untouched: one dataset, both facts.
    assert any(
        e["@type"] == "prov:wasGeneratedBy"
        and e["ds:source"] == CATALOGUE_EVENT["data_product_id"]
        for e in edges
    )


@pytest.mark.asyncio
async def test_a_withdrawal_keeps_what_the_publication_said_about_the_dataset(client):
    """`upsert_node` skips `None`, and this is where that matters.

    The withdrawal names the dataset to invalidate it and knows nothing about
    its title — so it must not blank the one the publication recorded.
    """
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=WITHDRAWAL_EVENT)

    entities = (await client.get("/prov/entities")).json()["@graph"]
    dataset = next(
        n for n in entities if n["@id"] == CATALOGUE_EVENT["data_product_id"]
    )
    assert dataset.get("prov:label") == CATALOGUE_EVENT["title"]


@pytest.mark.asyncio
async def test_ingest_contract_agreement(client):
    response = await client.post("/prov/events", json=CONTRACT_EVENT)
    assert response.status_code == 201
    assert response.json()["status"] == "created"


@pytest.mark.asyncio
async def test_ingest_data_transfer(client):
    response = await client.post("/prov/events", json=TRANSFER_EVENT)
    assert response.status_code == 201
    assert response.json()["status"] == "created"


@pytest.mark.rule("L-15")
@pytest.mark.asyncio
async def test_an_unknown_event_type_is_refused(client):
    """`UsageObligationFulfilled` used to be accepted here, and was **deleted**
    2026-08-09 rather than given the emitter it never had.

    It was a *consumer* reporting that it met an obligation. A provider cannot
    verify such a report — the obligations this platform declares (notify on
    access, anonymise before use, retention) are ones no third party can attest —
    so the record's only content would have been that somebody said so.
    `L-15` says an event type with no emitter does not exist; this asserts the
    schema now agrees, which is also the guard against it being re-added as a
    write-only surface.
    """
    response = await client.post(
        "/prov/events",
        json={
            "event_type": "UsageObligationFulfilled",
            "occurred_at": "2026-01-01T00:00:00Z",
            "agreement_id": "agr-1",
            "consumer_did": "did:web:third-party.dataspaces.localhost",
            "obligation_type": "odrl:delete",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_events_by_type(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=CONTRACT_EVENT)

    response = await client.get("/prov/events?event_type=CataloguePublished")
    assert response.status_code == 200
    body = response.json()
    assert len(body["@graph"]) >= 1
    for evt in body["@graph"]:
        assert "CataloguePublished" in evt["@type"]
