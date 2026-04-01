"""Tests for /prov/entities, /prov/activities, /prov/agents endpoints."""
import urllib.parse

import pytest


@pytest.mark.asyncio
async def test_create_entity(client):
    payload = {
        "iri": "https://provider.dataspaces.localhost/datasets/meters_15m",
        "label": "Meter Readings 15m",
        "energy_type": "ConsumptionMeasurement",
    }
    response = await client.post("/prov/entities", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert "@graph" in body
    node = body["@graph"][0]
    assert node["@id"] == payload["iri"]
    assert "prov:Entity" in (
        node["@type"] if isinstance(node["@type"], list) else [node["@type"]]
    )


@pytest.mark.asyncio
async def test_create_entity_duplicate_returns_existing(client):
    payload = {
        "iri": "https://provider.dataspaces.localhost/datasets/meters_15m_dup",
        "label": "Meter Readings 15m",
    }
    r1 = await client.post("/prov/entities", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/prov/entities", json=payload)
    # upsert — same IRI returns existing node
    assert r2.status_code in (200, 201)
    assert r1.json()["@graph"][0]["@id"] == r2.json()["@graph"][0]["@id"]


@pytest.mark.asyncio
async def test_create_activity(client):
    payload = {
        "iri": "urn:uuid:activity-001",
        "label": "CatalogPublication",
        "started_at": "2026-01-01T00:00:00Z",
    }
    response = await client.post("/prov/activities", json=payload)
    assert response.status_code == 201
    node = response.json()["@graph"][0]
    assert node["@type"] == "prov:Activity"


@pytest.mark.asyncio
async def test_create_agent(client):
    payload = {
        "iri": "did:web:provider.dataspaces.localhost",
        "label": "Provider",
    }
    response = await client.post("/prov/agents", json=payload)
    assert response.status_code == 201
    node = response.json()["@graph"][0]
    assert node["@type"] == "prov:Agent"


@pytest.mark.asyncio
async def test_list_entities(client):
    iri = "https://provider.dataspaces.localhost/datasets/grid_freq"
    await client.post("/prov/entities", json={"iri": iri, "label": "Grid Frequency"})
    response = await client.get("/prov/entities")
    assert response.status_code == 200
    body = response.json()
    assert "@graph" in body
    iris = [n["@id"] for n in body["@graph"]]
    assert iri in iris


@pytest.mark.asyncio
async def test_soft_delete_entity(client):
    iri = "https://provider.dataspaces.localhost/datasets/to_delete"
    await client.post("/prov/entities", json={"iri": iri})

    encoded = urllib.parse.quote(iri, safe="")
    delete = await client.delete(f"/prov/entities/{encoded}")
    assert delete.status_code == 204
