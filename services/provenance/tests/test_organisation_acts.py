"""An organisation acting as itself is attributable (DSSC-XCT-09, 2026-09-17).

An organisation's own client may negotiate and transfer on the consumer side.
There is no person to name, so the act carries `acted_by`: the client that acted
(`client_id`), with the organisation's participant context as `sub`, acting on
behalf of that organisation — a legal person, and the accountable party. The
graph must answer both "which client" and "for which organisation".
"""

from __future__ import annotations

import urllib.parse

import pytest

ORG = "did:web:consumer.test"
ISSUER = "https://keycloak.test/realms/dataspaces"
ACTED_BY = {
    "subject": ORG,
    "issuer": ISSUER,
    "on_behalf_of": ORG,
    "is_service": True,
    "client_id": "svc-ds-connector-consumer",
}
PRINCIPAL = f"urn:ds:principal:{ISSUER}:{ORG}"

COMMON = {
    "occurred_at": "2026-09-17T10:00:00Z",
    "data_product_id": "urn:dataset:open",
    "provider_did": "did:web:provider.test",
    "consumer_did": ORG,
}

EVENTS = {
    "AccessRequested": {"request_id": "req-org-1"},
    "NegotiationStarted": {"negotiation_id": "neg-org-1"},
    "TransferStarted": {"transfer_id": "tp-org-1", "agreement_id": "ag-org-1"},
    "AccessRevoked": {"agreement_id": "ag-org-1", "transfer_id": "tp-org-1"},
}


def _event(kind: str, **over) -> dict:
    body = {"event_type": kind, "event_id": f"org-{kind}", **COMMON, **EVENTS[kind]}
    body["acted_by"] = ACTED_BY
    body.update(over)
    return body


async def _agents(client) -> dict[str, dict]:
    body = (await client.get("/prov/agents")).json()
    return {node["@id"]: node for node in body["@graph"]}


@pytest.mark.rule("L-5")
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(EVENTS))
async def test_an_organisation_s_act_names_its_client(client, kind):
    r = await client.post("/prov/events", json=_event(kind))
    assert r.status_code == 201, r.text

    agents = await _agents(client)
    assert PRINCIPAL in agents
    assert agents[PRINCIPAL]["isService"] is True
    assert agents[PRINCIPAL]["clientId"] == "svc-ds-connector-consumer"


@pytest.mark.rule("L-5")
@pytest.mark.asyncio
async def test_the_client_acted_on_behalf_of_the_organisation_itself(client):
    """The organisation node is the participant's DID — the node every other
    event names it with — not an `urn:ds:owner:` stand-in."""
    await client.post("/prov/events", json=_event("NegotiationStarted"))

    quoted = urllib.parse.quote(ORG, safe="")
    graph = (
        await client.get(f"/prov/lineage/{quoted}?direction=both&max_depth=3")
    ).json()["@graph"]
    delegation = [i for i in graph if i.get("@type") == "prov:actedOnBehalfOf"]
    assert delegation and delegation[0]["ds:target"] == ORG


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,field", [("AccessRequested", "user_did"), ("AccessRevoked", "subject_id")]
)
async def test_an_act_naming_nobody_is_refused(client, kind, field):
    """No person and no principal is not an act anyone performed."""
    body = _event(kind)
    body.pop("acted_by")
    body.pop(field, None)
    r = await client.post("/prov/events", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_person_s_request_still_needs_no_principal(client):
    body = _event("AccessRequested", user_did="did:web:consumer.test:users:u-1")
    body.pop("acted_by")
    assert (await client.post("/prov/events", json=body)).status_code == 201
