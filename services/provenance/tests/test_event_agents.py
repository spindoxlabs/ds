"""Rulebook `L-5` — every principal an event names becomes an agent in the graph.

Three were named and materialised into nothing: the data subject on
`AccessRevoked`, and `acted_by` on `CataloguePublished` and `DataIngested`. All
three were validated and stored verbatim in the payload, so they *looked*
recorded; the graph — the thing lineage and the portal read — could not answer
"whose access was revoked" or "who published this offer".
"""
from __future__ import annotations

import urllib.parse

import pytest

SUBJECT = "did:example:subject-1"

REVOKED_EVENT = {
    "event_type": "AccessRevoked",
    "event_id": "agents-revoked-1",
    "occurred_at": "2026-04-01T10:00:00Z",
    "agreement_id": "urn:uuid:agr-9",
    "data_product_id": "urn:dataset:meters",
    "provider_did": "did:web:provider.test",
    "consumer_did": "did:web:consumer.test",
    "subject_id": SUBJECT,
    "reason": "consent withdrawn",
}

PUBLISHED_BY_A_PERSON = {
    "event_type": "CataloguePublished",
    "event_id": "agents-pub-1",
    "occurred_at": "2026-04-02T10:00:00Z",
    "data_product_id": "urn:dataset:published",
    "provider_did": "did:web:provider.test",
    "title": "Published by a person",
    "acted_by": {
        "subject": "f7c1-opaque-sub",
        "issuer": "https://keycloak.test/realms/dataspaces",
        "on_behalf_of": "example-org",
        "is_service": False,
    },
}


async def _agents(client) -> dict[str, dict]:
    body = (await client.get("/prov/agents")).json()
    return {node["@id"]: node for node in body["@graph"]}


async def _lineage(client, iri: str) -> list[dict]:
    quoted = urllib.parse.quote(iri, safe="")
    response = await client.get(f"/prov/lineage/{quoted}?direction=both&max_depth=3")
    assert response.status_code == 200
    return response.json()["@graph"]


@pytest.mark.asyncio
async def test_access_revoked_names_the_subject_as_an_agent(client):
    assert (await client.post("/prov/events", json=REVOKED_EVENT)).status_code == 201

    assert SUBJECT in await _agents(client)


@pytest.mark.asyncio
async def test_the_subject_edge_is_distinguishable_from_the_two_parties(client):
    """Provider, consumer and subject are all `wasAssociatedWith` the revocation,
    and they are not the same kind of participation. `prov:role` is what a reader
    uses to tell "performed it" from "it was about them"."""
    await client.post("/prov/events", json=REVOKED_EVENT)

    graph = await _lineage(client, f"urn:activity:access-revocation:{REVOKED_EVENT['event_id']}")
    subject_edges = [
        item for item in graph
        if item.get("ds:target") == SUBJECT and "@type" in item
    ]
    assert subject_edges, "the subject is in the graph but nothing links it to the revocation"
    assert subject_edges[0]["prov:role"] == "dataSubject"

    party_edges = [
        item for item in graph if item.get("ds:target") == "did:web:provider.test"
    ]
    assert party_edges and "prov:role" not in party_edges[0]


@pytest.mark.asyncio
async def test_acted_by_becomes_a_pseudonymous_agent(client):
    assert (await client.post("/prov/events", json=PUBLISHED_BY_A_PERSON)).status_code == 201

    agents = await _agents(client)
    iri = "urn:ds:principal:https://keycloak.test/realms/dataspaces:f7c1-opaque-sub"
    assert iri in agents
    actor = agents[iri]
    # The realm is recorded with the subject, because a `sub` is only unique
    # within the realm that minted it.
    assert actor["issuer"] == "https://keycloak.test/realms/dataspaces"
    assert actor["isService"] is False
    # …and nothing beyond the opaque identifier.
    assert "@example" not in str(actor)


@pytest.mark.asyncio
async def test_acted_on_behalf_of_is_an_edge_not_a_string(client):
    """"Acting for whom" is the second half of the Art. 5(2) question, and it is
    only answerable if the owner is a node with an edge to the actor."""
    await client.post("/prov/events", json=PUBLISHED_BY_A_PERSON)

    graph = await _lineage(client, "urn:ds:owner:example-org")
    delegation = [item for item in graph if item.get("@type") == "prov:actedOnBehalfOf"]
    assert delegation, "no actedOnBehalfOf edge for an owner-scoped publication"
    assert delegation[0]["ds:target"] == "urn:ds:owner:example-org"


@pytest.mark.asyncio
async def test_an_automated_publish_is_recorded_as_one(client):
    """`is_service` exists so an automated publish is not read as a person's
    decision — it has to reach the graph for that to hold."""
    event = dict(
        PUBLISHED_BY_A_PERSON,
        event_id="agents-pub-2",
        data_product_id="urn:dataset:auto",
        acted_by={"subject": "svc-sub", "issuer": None, "is_service": True},
    )
    await client.post("/prov/events", json=event)

    agents = await _agents(client)
    assert agents["urn:ds:principal:svc-sub"]["isService"] is True

    graph = await _lineage(client, "urn:ds:principal:svc-sub")
    edge = [item for item in graph if item.get("ds:target") == "urn:ds:principal:svc-sub"]
    assert edge[0]["prov:role"] == "service"


@pytest.mark.asyncio
async def test_data_ingested_records_who_decided_to(client):
    event = {
        "event_type": "DataIngested",
        "event_id": "agents-ingest-1",
        "occurred_at": "2026-04-03T10:00:00Z",
        "dataset_id": "urn:dataset:offline",
        "provider_did": "did:web:provider.test",
        "record_count": 10,
        "acted_by": {"subject": "operator-sub", "is_service": False},
    }
    assert (await client.post("/prov/events", json=event)).status_code == 201

    assert "urn:ds:principal:operator-sub" in await _agents(client)


@pytest.mark.asyncio
async def test_an_event_without_a_principal_adds_no_agent(client):
    """`acted_by` is optional so a deployment that predates it keeps validating.
    Absent must mean absent, not an agent standing in for nobody."""
    plain = {
        "event_type": "CataloguePublished",
        "event_id": "agents-pub-3",
        "occurred_at": "2026-04-04T10:00:00Z",
        "data_product_id": "urn:dataset:plain",
        "provider_did": "did:web:provider.test",
    }
    await client.post("/prov/events", json=plain)

    assert not [iri for iri in await _agents(client) if iri.startswith("urn:ds:principal:")]
