"""Tests for /prov/relations endpoint."""
import pytest


@pytest.mark.asyncio
async def test_create_relation(client):
    await client.post(
        "/prov/entities",
        json={"iri": "https://example.com/ds/001", "label": "Dataset 001"},
    )
    await client.post(
        "/prov/agents",
        json={"iri": "did:web:provider.example", "label": "Provider"},
    )

    relation = await client.post(
        "/prov/relations",
        json={
            "relation_type": "wasAttributedTo",
            "subject_iri": "https://example.com/ds/001",
            "object_iri": "did:web:provider.example",
        },
    )
    assert relation.status_code == 201
    body = relation.json()
    assert "@graph" in body
    edge = body["@graph"][0]
    assert "wasAttributedTo" in str(edge.get("@type", ""))


@pytest.mark.asyncio
async def test_duplicate_relation_returns_409(client):
    await client.post(
        "/prov/entities",
        json={"iri": "https://example.com/ds/002"},
    )
    await client.post(
        "/prov/agents",
        json={"iri": "did:web:agent.example"},
    )

    rel_payload = {
        "relation_type": "wasAttributedTo",
        "subject_iri": "https://example.com/ds/002",
        "object_iri": "did:web:agent.example",
    }
    r1 = await client.post("/prov/relations", json=rel_payload)
    assert r1.status_code == 201
    r2 = await client.post("/prov/relations", json=rel_payload)
    assert r2.status_code == 409
