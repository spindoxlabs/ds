"""The node collections, made symmetric and bounded.

Three collections, three different surfaces: entities could be read one at a time
and deleted, activities could be read but not deleted, agents could be neither.
All three are now created and read, and none is deleted (`L-17`).
And all three listings took an unbounded `limit`/`offset` while `GET /prov/events`
next door has always capped them.
"""

from __future__ import annotations

import urllib.parse

import pytest


def _q(iri: str) -> str:
    return urllib.parse.quote(iri, safe="")


@pytest.mark.asyncio
async def test_an_agent_can_be_read_by_iri(client):
    iri = "did:web:rec.dataspaces.localhost"
    await client.post("/prov/agents", json={"iri": iri, "label": "Provider"})

    response = await client.get(f"/prov/agents/{_q(iri)}")
    assert response.status_code == 200
    assert response.json()["@graph"][0]["@id"] == iri


@pytest.mark.asyncio
async def test_the_agent_listing_is_still_reachable(client):
    """`/agents/{iri:path}` is declared after `/agents`; the other order makes the
    catch-all swallow the listing."""
    await client.post("/prov/agents", json={"iri": "did:web:a.test"})
    response = await client.get("/prov/agents")
    assert response.status_code == 200
    assert [n["@id"] for n in response.json()["@graph"]] == ["did:web:a.test"]


@pytest.mark.asyncio
@pytest.mark.rule("L-17")
@pytest.mark.parametrize(
    "collection,payload",
    [
        ("entities", {"iri": "urn:dataset:kept", "label": "Kept"}),
        ("activities", {"iri": "urn:activity:kept", "label": "Kept"}),
        ("agents", {"iri": "did:web:kept.test", "label": "Kept"}),
    ],
)
async def test_no_collection_can_be_deleted_from(client, collection, payload):
    """The record is append-only. The `DELETE` routes soft-deleted a node for any
    holder of `provenance.write`; they are gone, and the node stays listed."""
    await client.post(f"/prov/{collection}", json=payload)

    assert (
        await client.delete(f"/prov/{collection}/{_q(payload['iri'])}")
    ).status_code == 405
    listed = (await client.get(f"/prov/{collection}")).json()["@graph"]
    assert payload["iri"] in [n["@id"] for n in listed]


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["entities", "activities", "agents"])
async def test_the_listings_are_bounded(client, collection):
    assert (await client.get(f"/prov/{collection}?limit=100000")).status_code == 422
    assert (await client.get(f"/prov/{collection}?limit=0")).status_code == 422
    assert (await client.get(f"/prov/{collection}?offset=-1")).status_code == 422
    assert (await client.get(f"/prov/{collection}?limit=500")).status_code == 200
