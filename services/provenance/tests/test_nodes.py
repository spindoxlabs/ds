"""Tests for /prov/entities, /prov/activities, /prov/agents endpoints."""

import urllib.parse

import pytest


@pytest.mark.asyncio
async def test_create_entity(client):
    payload = {
        "iri": "https://rec.dataspaces.localhost/datasets/meters_15m",
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
@pytest.mark.rule("L-17")
async def test_create_entity_duplicate_returns_existing_unchanged(client):
    """Create-only: a second `POST` is a 409 with the node as recorded, and it
    changes nothing. It used to overwrite the label of whatever it named."""
    iri = "https://rec.dataspaces.localhost/datasets/meters_15m_dup"
    r1 = await client.post("/prov/entities", json={"iri": iri, "label": "Meter Readings 15m"})
    assert r1.status_code == 201
    r2 = await client.post("/prov/entities", json={"iri": iri, "label": "Rewritten"})
    assert r2.status_code == 409
    assert r2.json()["@graph"][0]["@id"] == iri
    stored = await client.get(f"/prov/entities/{urllib.parse.quote(iri, safe='')}")
    assert stored.json()["@graph"][0]["prov:label"] == "Meter Readings 15m"


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
        "iri": "did:web:rec.dataspaces.localhost",
        "label": "Provider",
    }
    response = await client.post("/prov/agents", json=payload)
    assert response.status_code == 201
    node = response.json()["@graph"][0]
    assert node["@type"] == "prov:Agent"


@pytest.mark.asyncio
async def test_list_entities(client):
    iri = "https://rec.dataspaces.localhost/datasets/grid_freq"
    await client.post("/prov/entities", json={"iri": iri, "label": "Grid Frequency"})
    response = await client.get("/prov/entities")
    assert response.status_code == 200
    body = response.json()
    assert "@graph" in body
    iris = [n["@id"] for n in body["@graph"]]
    assert iri in iris


