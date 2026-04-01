"""Tests for domain event ingest and PROV-O materialisation."""
import pytest


CATALOGUE_EVENT = {
    "event_type": "CataloguePublished",
    "event_id": "test-cat-001",
    "occurred_at": "2026-01-01T10:00:00Z",
    "data_product_id": "https://provider.dataspaces.localhost/datasets/meters_15m",
    "provider_did": "did:web:provider.dataspaces.localhost",
    "title": "Meter Readings 15m",
}

CONTRACT_EVENT = {
    "event_type": "ContractAgreementSigned",
    "event_id": "test-contract-001",
    "occurred_at": "2026-01-02T10:00:00Z",
    "agreement_id": "urn:uuid:agreement-001",
    "data_product_id": "https://provider.dataspaces.localhost/datasets/meters_15m",
    "provider_did": "did:web:provider.dataspaces.localhost",
    "consumer_did": "did:web:consumer.dataspaces.localhost",
}

TRANSFER_EVENT = {
    "event_type": "DataTransferCompleted",
    "event_id": "test-transfer-001",
    "occurred_at": "2026-01-03T10:00:00Z",
    "transfer_id": "urn:uuid:transfer-001",
    "agreement_id": "urn:uuid:agreement-001",
    "data_product_id": "https://provider.dataspaces.localhost/datasets/meters_15m",
    "provider_did": "did:web:provider.dataspaces.localhost",
    "consumer_did": "did:web:consumer.dataspaces.localhost",
    "bytes_transferred": 4096,
}

OBLIGATION_EVENT = {
    "event_type": "UsageObligationFulfilled",
    "event_id": "test-obligation-001",
    "occurred_at": "2026-01-04T10:00:00Z",
    "agreement_id": "urn:uuid:agreement-001",
    "consumer_did": "did:web:consumer.dataspaces.localhost",
    "obligation_type": "odrl:delete",
}


@pytest.mark.asyncio
async def test_ingest_catalogue_published(client):
    response = await client.post("/prov/events", json=CATALOGUE_EVENT)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    assert body["event_id"] == CATALOGUE_EVENT["event_id"]
    assert body["prov_node_id"] is not None


@pytest.mark.asyncio
async def test_ingest_duplicate_is_idempotent(client):
    r1 = await client.post("/prov/events", json=CATALOGUE_EVENT)
    assert r1.status_code == 201
    r2 = await client.post("/prov/events", json=CATALOGUE_EVENT)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


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


@pytest.mark.asyncio
async def test_ingest_obligation_fulfilled(client):
    response = await client.post("/prov/events", json=OBLIGATION_EVENT)
    assert response.status_code == 201
    assert response.json()["status"] == "created"


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
