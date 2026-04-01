"""Tests for lineage traversal."""
import pytest

CATALOGUE_EVENT = {
    "event_type": "CataloguePublished",
    "event_id": "lineage-cat-001",
    "occurred_at": "2026-01-01T10:00:00Z",
    "data_product_id": "https://provider.dataspaces.localhost/datasets/grid_freq",
    "provider_did": "did:web:provider.dataspaces.localhost",
    "title": "Grid Frequency",
}

TRANSFER_EVENT = {
    "event_type": "DataTransferCompleted",
    "event_id": "lineage-transfer-001",
    "occurred_at": "2026-01-03T10:00:00Z",
    "transfer_id": "urn:uuid:lt-001",
    "agreement_id": "urn:uuid:lagr-001",
    "data_product_id": "https://provider.dataspaces.localhost/datasets/grid_freq",
    "provider_did": "did:web:provider.dataspaces.localhost",
    "consumer_did": "did:web:consumer.dataspaces.localhost",
    "derived_dataset_iri": "https://consumer.dataspaces.localhost/datasets/grid_freq_copy",
}


@pytest.mark.asyncio
async def test_lineage_returns_graph(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=TRANSFER_EVENT)

    import urllib.parse
    iri = urllib.parse.quote(
        "https://provider.dataspaces.localhost/datasets/grid_freq", safe=""
    )
    response = await client.get(f"/prov/lineage/{iri}?direction=both&max_depth=5")
    assert response.status_code == 200
    body = response.json()
    assert "@context" in body
    assert "@graph" in body
    assert "root" in body


@pytest.mark.asyncio
async def test_lineage_unknown_iri_returns_empty(client):
    import urllib.parse
    iri = urllib.parse.quote("https://unknown.example/datasets/nope", safe="")
    response = await client.get(f"/prov/lineage/{iri}")
    # Either 200 with empty graph or 404 — both acceptable
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_lineage_downstream(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=TRANSFER_EVENT)

    import urllib.parse
    iri = urllib.parse.quote(
        "https://provider.dataspaces.localhost/datasets/grid_freq", safe=""
    )
    response = await client.get(f"/prov/lineage/{iri}?direction=downstream")
    assert response.status_code == 200
