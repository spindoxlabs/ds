"""Lineage traversal — the response envelope and the not-found contract.

Direction is `test_lineage_direction.py`. What is here used to assert nothing
decidable: that `@graph` was a key (true of an empty graph), and that an unknown
IRI answered "200 **or** 404" — which is every outcome the route can produce, so
the test could not fail whatever the code did.
"""
import urllib.parse

import pytest

DATASET = "https://provider.dataspaces.localhost/datasets/grid_freq"

CATALOGUE_EVENT = {
    "event_type": "CataloguePublished",
    "event_id": "lineage-cat-001",
    "occurred_at": "2026-01-01T10:00:00Z",
    "data_product_id": DATASET,
    "provider_did": "did:web:provider.dataspaces.localhost",
    "title": "Grid Frequency",
}

TRANSFER_EVENT = {
    "event_type": "DataTransferCompleted",
    "event_id": "lineage-transfer-001",
    "occurred_at": "2026-01-03T10:00:00Z",
    "transfer_id": "urn:uuid:lt-001",
    "agreement_id": "urn:uuid:lagr-001",
    "data_product_id": DATASET,
    "provider_did": "did:web:provider.dataspaces.localhost",
    "consumer_did": "did:web:consumer.dataspaces.localhost",
    "derived_dataset_iri": "https://consumer.dataspaces.localhost/datasets/grid_freq_copy",
}


@pytest.mark.asyncio
async def test_lineage_returns_the_root_its_depth_and_a_populated_graph(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=TRANSFER_EVENT)

    iri = urllib.parse.quote(DATASET, safe="")
    response = await client.get(f"/prov/lineage/{iri}?direction=both&max_depth=5")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")

    body = response.json()
    assert body["root"] == DATASET
    assert body["direction"] == "both"
    assert body["depth"] >= 1
    assert body["@context"].endswith("/prov/context")

    graph = body["@graph"]
    assert DATASET in [item["@id"] for item in graph]
    assert any("ds:source" in item for item in graph), "nodes but no edges"


@pytest.mark.asyncio
async def test_an_unknown_iri_is_a_404_not_an_empty_graph(client):
    """An empty graph and "no such node" are different answers, and a caller
    branches on them differently."""
    iri = urllib.parse.quote("https://unknown.example/datasets/nope", safe="")
    response = await client.get(f"/prov/lineage/{iri}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_the_query_parameters_are_bounded(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    iri = urllib.parse.quote(DATASET, safe="")

    assert (await client.get(f"/prov/lineage/{iri}?max_depth=21")).status_code == 422
    assert (await client.get(f"/prov/lineage/{iri}?max_depth=0")).status_code == 422
    assert (await client.get(f"/prov/lineage/{iri}?direction=sideways")).status_code == 422


@pytest.mark.asyncio
async def test_relation_types_narrow_the_walk(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=TRANSFER_EVENT)
    iri = urllib.parse.quote(DATASET, safe="")

    body = (
        await client.get(f"/prov/lineage/{iri}?direction=both&relation_types=wasDerivedFrom")
    ).json()
    types = {item["@type"] for item in body["@graph"] if "ds:source" in item}
    assert types == {"prov:wasDerivedFrom"}
