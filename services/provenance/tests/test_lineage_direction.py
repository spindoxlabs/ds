"""`direction` has to mean three different things, and it used to mean two.

Every edge this service writes points backwards in time — `wasGeneratedBy(dataset,
activity)`, `wasDerivedFrom(copy, source)` — so walking subject→object is
**upstream** and object→subject is **downstream**. `downstream` selected both,
which made it a synonym for `both`: a caller asking "what came out of this
dataset" was handed its provenance as well, with nothing in the response saying
so.
"""

from __future__ import annotations

import urllib.parse

import pytest

DATASET = "https://rec.dataspaces.localhost/datasets/grid_freq"
DERIVED = "https://third-party.dataspaces.localhost/datasets/grid_freq_copy"
PUBLICATION = f"urn:activity:catalogue-publication:{DATASET}"

CATALOGUE_EVENT = {
    "event_type": "CataloguePublished",
    "event_id": "dir-cat-001",
    "occurred_at": "2026-01-01T10:00:00Z",
    "data_product_id": DATASET,
    "provider_did": "did:web:rec.dataspaces.localhost",
    "title": "Grid Frequency",
}

TRANSFER_EVENT = {
    "event_type": "DataTransferCompleted",
    "event_id": "dir-transfer-001",
    "occurred_at": "2026-01-03T10:00:00Z",
    "transfer_id": "urn:uuid:dt-001",
    "agreement_id": "urn:uuid:dagr-001",
    "data_product_id": DATASET,
    "provider_did": "did:web:rec.dataspaces.localhost",
    "consumer_did": "did:web:third-party.dataspaces.localhost",
    "derived_dataset_iri": DERIVED,
}


async def _seed(client):
    await client.post("/prov/events", json=CATALOGUE_EVENT)
    await client.post("/prov/events", json=TRANSFER_EVENT)


async def _iris(client, direction: str) -> set[str]:
    iri = urllib.parse.quote(DATASET, safe="")
    response = await client.get(
        f"/prov/lineage/{iri}?direction={direction}&max_depth=5"
    )
    assert response.status_code == 200
    return {item["@id"] for item in response.json()["@graph"]}


@pytest.mark.asyncio
async def test_upstream_reaches_how_the_dataset_came_to_be(client):
    await _seed(client)
    iris = await _iris(client, "upstream")
    assert PUBLICATION in iris
    assert DERIVED not in iris


@pytest.mark.asyncio
async def test_downstream_reaches_what_was_made_from_it_and_nothing_else(client):
    await _seed(client)
    iris = await _iris(client, "downstream")
    assert DERIVED in iris
    # The defect: `downstream` selected both directions, so the dataset's own
    # publication came back as if it were something derived from the dataset.
    assert PUBLICATION not in iris


@pytest.mark.asyncio
async def test_both_is_the_union_and_is_still_wider_than_either(client):
    await _seed(client)
    both = await _iris(client, "both")
    assert PUBLICATION in both
    assert DERIVED in both
    assert both >= (await _iris(client, "upstream")) | (
        await _iris(client, "downstream")
    )


@pytest.mark.asyncio
async def test_each_edge_appears_once(client):
    """Nodes were deduplicated by the visited set and edges by nothing, so an edge
    the walk reached from both ends came back once per round that touched it. The
    portal draws what it is given, so the graph rendered denser than the record.
    Found on the live dev graph: 89 entries for 48 edges."""
    await _seed(client)
    iri = urllib.parse.quote(DATASET, safe="")
    graph = (
        await client.get(f"/prov/lineage/{iri}?direction=both&max_depth=5")
    ).json()["@graph"]

    edge_ids = [item["@id"] for item in graph if "ds:source" in item]
    assert len(edge_ids) == len(set(edge_ids))

    node_ids = [item["@id"] for item in graph if "ds:source" not in item]
    assert len(node_ids) == len(set(node_ids))


@pytest.mark.asyncio
async def test_the_graph_carries_edges_not_only_nodes(client):
    """The lineage tests used to assert only that `@graph` was a key. A graph of
    nodes with no edges is exactly what the portal rendered for months."""
    await _seed(client)
    iri = urllib.parse.quote(DATASET, safe="")
    graph = (await client.get(f"/prov/lineage/{iri}?direction=both")).json()["@graph"]

    edges = [item for item in graph if "ds:source" in item]
    assert edges, "no edges in the lineage graph"
    assert {e["@type"] for e in edges} >= {"prov:wasGeneratedBy", "prov:wasDerivedFrom"}
    for edge in edges:
        assert edge["ds:source"] and edge["ds:target"]
