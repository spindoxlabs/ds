"""Rulebook `L-4` — an event is recorded once, and re-posting it is a no-op.

A caller that omitted `event_id` was handed a fresh UUID on every post, so the
idempotency check could never match. Emission is non-fatal and therefore
retried, which made a duplicate the *ordinary* outcome of a timeout, not an edge
case: the same disclosure counted twice in every reading of the log.
"""
from __future__ import annotations

import pytest

from provenance.schemas.events import CataloguePublished
from provenance.services.event_service import content_event_id

ANONYMOUS_EVENT = {
    "event_type": "CataloguePublished",
    "occurred_at": "2026-02-01T10:00:00Z",
    "data_product_id": "urn:dataset:no-id",
    "provider_did": "did:web:provider.test",
    "title": "No caller id",
}


@pytest.mark.rule("L-4")
@pytest.mark.asyncio
async def test_an_event_without_an_id_is_stored_once(client):
    first = await client.post("/prov/events", json=ANONYMOUS_EVENT)
    assert first.status_code == 201
    assert first.json()["status"] == "created"

    second = await client.post("/prov/events", json=ANONYMOUS_EVENT)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["event_id"] == first.json()["event_id"]

    listed = (await client.get("/prov/events?dataset_id=urn:dataset:no-id")).json()
    assert listed["hydra:totalItems"] == 1


@pytest.mark.rule("L-4")
@pytest.mark.asyncio
async def test_the_derived_key_is_visibly_derived(client):
    """A `sha256:` prefix separates a key this service computed from one a caller
    supplied — which is what tells an operator who is retrying without an id."""
    response = await client.post("/prov/events", json=ANONYMOUS_EVENT)
    assert response.json()["event_id"].startswith("sha256:")


@pytest.mark.rule("L-4")
@pytest.mark.asyncio
async def test_two_events_that_differ_are_two_events(client):
    later = dict(ANONYMOUS_EVENT, occurred_at="2026-02-01T11:00:00Z")
    assert (await client.post("/prov/events", json=ANONYMOUS_EVENT)).status_code == 201
    assert (await client.post("/prov/events", json=later)).status_code == 201

    listed = (await client.get("/prov/events?dataset_id=urn:dataset:no-id")).json()
    assert listed["hydra:totalItems"] == 2


@pytest.mark.rule("L-4")
@pytest.mark.asyncio
async def test_a_caller_supplied_id_still_wins(client):
    """The derived key is a fallback, not a replacement: a caller that manages its
    own idempotency keys keeps deciding what "the same event" means."""
    named = dict(ANONYMOUS_EVENT, event_id="caller-owned-1")
    assert (await client.post("/prov/events", json=named)).status_code == 201
    assert (await client.post("/prov/events", json=named)).status_code == 200

    listed = (await client.get("/prov/events?dataset_id=urn:dataset:no-id")).json()
    assert listed["@graph"][0]["@id"]  # stored under the caller's key, not a hash


@pytest.mark.rule("L-4")
def test_the_key_ignores_event_id_itself():
    """Otherwise the same event posted with and without an id would hash apart,
    and the fallback would not deduplicate against a named post of the same fact."""
    without = CataloguePublished.model_validate(ANONYMOUS_EVENT)
    with_id = CataloguePublished.model_validate(dict(ANONYMOUS_EVENT, event_id="x"))
    assert content_event_id(without) == content_event_id(with_id)


@pytest.mark.rule("L-4")
def test_the_key_is_stable_across_key_order():
    """Canonical JSON, not `str(dict)` — otherwise the key depends on field order
    and a model reshuffle silently re-admits every past event."""
    a = CataloguePublished.model_validate(ANONYMOUS_EVENT)
    b = CataloguePublished.model_validate(
        {
            "title": "No caller id",
            "provider_did": "did:web:provider.test",
            "data_product_id": "urn:dataset:no-id",
            "occurred_at": "2026-02-01T10:00:00Z",
            "event_type": "CataloguePublished",
        }
    )
    assert content_event_id(a) == content_event_id(b)
