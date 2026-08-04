"""GET /prov/events — projection, filters, paging — and GET /prov/my/events.

The projection is the part that had been silently lossy: the route emitted four
fixed columns, so `ConsentGranted`, `DataIngested` and friends were stored in full
and served as four empty values. Nothing read the published events back, which is
why it went unnoticed.
"""
from __future__ import annotations

import pytest
from tests import make_headers

SUBJECT = "did:web:rec.dataspaces.localhost:users:alice"
OTHER_SUBJECT = "did:web:rec.dataspaces.localhost:users:bob"
DATASET = "datasets.silver.meters_15m"


def _consent_granted(event_id: str, *, subject: str = SUBJECT, at: str = "2026-02-01T10:00:00Z") -> dict:
    return {
        "event_type": "ConsentGranted",
        "event_id": event_id,
        "occurred_at": at,
        "subject_id": subject,
        "dataset_id": DATASET,
        "consumer_did": "*",
        "offer_id": "household-energy-flexibility",
        "purpose": ["FlexibilityResearch"],
        "controller": "example-org",
        "controller_role": "operator",
        "legal_basis": {"basis_iri": "https://w3id.org/dpv#Consent", "consent_text_version": "1.0"},
    }


async def _post(client, event: dict) -> None:
    r = await client.post("/prov/events", json=event)
    assert r.status_code in (200, 201), r.text


async def _graph(client, path: str = "/prov/events", **params) -> list[dict]:
    r = await client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()["@graph"]


# ── projection ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_projects_the_events_own_fields(client):
    """A field an event declares is published — not just the four shared columns."""
    await _post(client, _consent_granted("proj-1"))

    event = (await _graph(client, event_type="ConsentGranted"))[0]

    assert event["@type"] == "ds:ConsentGranted"
    assert event["ds:subjectId"] == SUBJECT
    assert event["ds:offerId"] == "household-energy-flexibility"
    assert event["ds:purpose"] == ["FlexibilityResearch"]
    assert event["ds:controllerRole"] == "operator"
    assert event["ds:legalBasis"]["consent_text_version"] == "1.0"


@pytest.mark.asyncio
async def test_keeps_the_normalised_column_keys(client):
    """`dataset_id` still publishes as `ds:dataProductId` too.

    The columns are the cross-type dimensions — `DataIngested.dataset_id` and
    `CataloguePublished.data_product_id` both land in `data_product_id` — so a
    reader that filters across types keeps working. Projecting only the payload
    would silently rename the key for some event types.
    """
    await _post(client, _consent_granted("proj-2"))

    event = (await _graph(client, event_type="ConsentGranted"))[0]

    assert event["ds:dataProductId"] == DATASET
    assert event["ds:datasetId"] == DATASET


@pytest.mark.asyncio
async def test_omits_empty_fields(client):
    """An absent optional field is left out rather than published as null."""
    await _post(client, _consent_granted("proj-3"))

    event = (await _graph(client, event_type="ConsentGranted"))[0]

    assert "ds:reason" not in event  # ConsentGranted has no reason


# ── filters ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filters_by_subject_and_dataset(client):
    await _post(client, _consent_granted("filt-1"))
    await _post(client, _consent_granted("filt-2", subject=OTHER_SUBJECT))

    mine = await _graph(client, subject_id=SUBJECT)
    assert [e["ds:subjectId"] for e in mine] == [SUBJECT]

    assert len(await _graph(client, dataset_id=DATASET)) == 2
    assert await _graph(client, dataset_id="datasets.nope") == []


@pytest.mark.asyncio
async def test_event_type_filter_is_repeatable(client):
    await _post(client, _consent_granted("filt-3"))
    await _post(client, {
        "event_type": "ConsentRevoked",
        "event_id": "filt-4",
        "occurred_at": "2026-02-02T10:00:00Z",
        "subject_id": SUBJECT,
        "dataset_id": DATASET,
    })

    both = await _graph(client, event_type=["ConsentGranted", "ConsentRevoked"])
    assert {e["@type"] for e in both} == {"ds:ConsentGranted", "ds:ConsentRevoked"}


@pytest.mark.asyncio
async def test_time_window_narrows(client):
    """`occurred_after` used to be accepted and ignored — a filter that appears to
    work is worse than one that is absent."""
    await _post(client, _consent_granted("time-1", at="2026-01-01T00:00:00Z"))
    await _post(client, _consent_granted("time-2", at="2026-06-01T00:00:00Z"))

    later = await _graph(client, occurred_after="2026-03-01T00:00:00Z")
    assert len(later) == 1

    earlier = await _graph(client, occurred_before="2026-03-01T00:00:00Z")
    assert len(earlier) == 1

    assert await _graph(
        client, occurred_after="2026-02-01T00:00:00Z", occurred_before="2026-03-01T00:00:00Z"
    ) == []


# ── paging ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paging_reports_the_total(client):
    for i in range(5):
        await _post(client, _consent_granted(f"page-{i}", at=f"2026-02-0{i + 1}T10:00:00Z"))

    r = await client.get("/prov/events", params={"limit": 2, "offset": 0})
    body = r.json()

    assert len(body["@graph"]) == 2
    # The count is of matching events, not of the page — a client cannot page
    # without knowing how far it goes.
    assert body["hydra:totalItems"] == 5
    assert body["hydra:limit"] == 2

    second = (await client.get("/prov/events", params={"limit": 2, "offset": 2})).json()
    assert {e["@id"] for e in second["@graph"]}.isdisjoint({e["@id"] for e in body["@graph"]})


@pytest.mark.asyncio
async def test_limit_is_bounded(client):
    assert (await client.get("/prov/events", params={"limit": 10_000})).status_code == 422
    assert (await client.get("/prov/events", params={"offset": -1})).status_code == 422


# ── the subject's own view ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_my_events_needs_a_credential(client):
    """No scope grants access here — the route authenticates a person."""
    r = await client.get("/prov/my/events")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_my_events_rejects_a_read_scope_alone(client):
    """A `provenance.read` token is not a data subject.

    Guards the split: if this route were ever mounted under the scoped router, a
    service token would silently read a person's history.
    """
    r = await client.get("/prov/my/events", headers=make_headers(scope="provenance.read"))
    assert r.status_code == 401
