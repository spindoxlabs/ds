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
    # 409 returns the existing edge, not an error body — which is why the route
    # now declares the status it has always been able to answer.
    assert r2.json()["@graph"][0]["@id"] == r1.json()["@graph"][0]["@id"]


@pytest.mark.asyncio
async def test_the_route_returns_the_same_edge_shape_as_lineage(client):
    """One edge, one serialisation. This route used to hand-roll `prov:subject` /
    `prov:object` — terms `PROV_CONTEXT` does not define — so the same edge looked
    different depending on which route returned it."""
    await client.post("/prov/entities", json={"iri": "https://example.com/ds/003"})
    await client.post("/prov/agents", json={"iri": "did:web:agent3.example"})

    response = await client.post(
        "/prov/relations",
        json={
            "relation_type": "wasAttributedTo",
            "subject_iri": "https://example.com/ds/003",
            "object_iri": "did:web:agent3.example",
        },
    )
    edge = response.json()["@graph"][0]
    assert edge["@type"] == "prov:wasAttributedTo"
    assert edge["ds:source"] == "https://example.com/ds/003"
    assert edge["ds:target"] == "did:web:agent3.example"
    assert edge["prov:entity"] == "https://example.com/ds/003"
    assert edge["prov:agent"] == "did:web:agent3.example"
    assert "prov:subject" not in edge


@pytest.mark.asyncio
async def test_the_ingest_paths_own_relation_type_is_accepted(client):
    """`invalidated` is written by two materialisers and was rejected here — the
    same edge legal through one door and a 422 through the other."""
    await client.post("/prov/activities", json={"iri": "urn:activity:revocation-1"})
    await client.post("/prov/entities", json={"iri": "urn:dataset:revoked"})

    response = await client.post(
        "/prov/relations",
        json={
            "relation_type": "invalidated",
            "subject_iri": "urn:activity:revocation-1",
            "object_iri": "urn:dataset:revoked",
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_an_unknown_relation_type_is_still_refused(client):
    response = await client.post(
        "/prov/relations",
        json={
            "relation_type": "wasInventedBy",
            "subject_iri": "urn:activity:revocation-1",
            "object_iri": "urn:dataset:revoked",
        },
    )
    assert response.status_code == 422
