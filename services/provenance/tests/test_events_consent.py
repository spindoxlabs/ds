"""PROV-O materialisation for the Block C consent & disclosure events."""
import pytest


CONSENT_GRANTED = {
    "event_type": "ConsentGranted",
    "event_id": "test-consent-granted-001",
    "occurred_at": "2026-02-01T10:00:00Z",
    "subject_id": "did:web:rec.dataspaces.localhost:users:alice",
    "dataset_id": "datasets.silver.meters_15m",
    "consumer_did": "*",
    "offer_id": "household-energy-flexibility",
    "purpose": ["FlexibilityResearch"],
    "controller": "example-org",
    "controller_role": "operator",
    "legal_basis": {"basis_iri": "https://w3id.org/dpv#Consent", "consent_text_version": "1.0"},
}

CONSENT_REVOKED = {
    "event_type": "ConsentRevoked",
    "event_id": "test-consent-revoked-001",
    "occurred_at": "2026-02-02T10:00:00Z",
    "subject_id": "did:web:rec.dataspaces.localhost:users:alice",
    "dataset_id": "datasets.silver.meters_15m",
    "consumer_did": "*",
    "offer_id": "household-energy-flexibility",
    "purpose": ["FlexibilityResearch"],
    "reason": "subject opted out",
}

DATA_INGESTED = {
    "event_type": "DataIngested",
    "event_id": "test-ingested-001",
    "occurred_at": "2026-02-03T10:00:00Z",
    "dataset_id": "datasets.silver.meters_15m",
    "provider_did": "did:web:rec.dataspaces.localhost",
    "source_ref": "dso-handover-2026-02",
    "record_count": 1234,
    "consent_snapshot_hash": "a" * 64,
    "agreement_ref": "dpa-participation-1.0",
}

DATA_DISCLOSED = {
    "event_type": "DataDisclosed",
    "event_id": "test-disclosed-001",
    "occurred_at": "2026-02-04T10:00:00Z",
    "dataset_id": "datasets.silver.meters_15m",
    "recipient_ref": "dso-org",
    "purpose": ["GridMonitoring"],
    "columns": ["pod_code", "consumption", "dataspace_did"],
    "subject_count": 10,
    "source_ref": "example-rec",
    "disclosed_by": "example-org",
    "consent_snapshot_hash": "b" * 64,
    "agreement_ref": "dpa-participation-1.0",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [CONSENT_GRANTED, CONSENT_REVOKED, DATA_INGESTED, DATA_DISCLOSED],
    ids=["granted", "revoked", "ingested", "disclosed"],
)
async def test_new_event_ingests(client, event):
    response = await client.post("/prov/events", json=event)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "created"
    assert body["prov_node_id"] is not None


@pytest.mark.asyncio
async def test_consent_granted_materialises_subject_and_dataset(client):
    await client.post("/prov/events", json=CONSENT_GRANTED)

    entities = await client.get("/prov/entities")
    entity_ids = [n["@id"] for n in entities.json()["@graph"]]
    assert CONSENT_GRANTED["dataset_id"] in entity_ids

    agents = await client.get("/prov/agents")
    agent_ids = [n["@id"] for n in agents.json()["@graph"]]
    assert CONSENT_GRANTED["subject_id"] in agent_ids

    activities = await client.get("/prov/activities")
    labels = [n.get("prov:label", "") for n in activities.json()["@graph"]]
    assert any("Consent Granted" in lbl for lbl in labels)


@pytest.mark.asyncio
async def test_data_disclosed_materialises_recipient_agent(client):
    await client.post("/prov/events", json=DATA_DISCLOSED)

    agents = await client.get("/prov/agents")
    agent_ids = [n["@id"] for n in agents.json()["@graph"]]
    assert DATA_DISCLOSED["recipient_ref"] in agent_ids
    assert DATA_DISCLOSED["disclosed_by"] in agent_ids


# ── L-2: the authorising consent state, or no record ──────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing", ["consent_snapshot_hash", "dataset_id"], ids=["no-hash", "no-dataset"]
)
async def test_a_disclosure_without_its_consent_evidence_is_refused(client, missing):
    """`L-2` asks a `DataDisclosed` to prove *which* consent state backed the
    handover. Both fields were optional, so an event omitting them was accepted
    and stored — indistinguishable, afterwards, from a disclosure made under no
    consent at all, and counted as a compliant record either way.

    They are one requirement, not two: a digest with no dataset id is a number
    nobody can recompute.
    """
    event = {k: v for k, v in DATA_DISCLOSED.items() if k != missing}

    response = await client.post("/prov/events", json=event)

    assert response.status_code == 422, response.text
    assert missing in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", ["", "unknown", "pending", "B" * 64, "b" * 63, "sha256:" + "b" * 64],
    ids=["empty", "unknown", "pending", "uppercase", "too-short", "prefixed"],
)
async def test_a_consent_hash_that_cannot_be_a_digest_is_refused(client, value):
    """Required is not enough on its own. A field typed `str` accepts
    `"unknown"` and `"pending"`, each of which satisfies "the field is present"
    while proving nothing — and `L-2` asks for a hash that can be **recomputed**.

    The accepted shape is exactly what `consent_service.consent_snapshot_hash`
    produces: `hashlib.sha256(...).hexdigest()`, bare and lowercase.
    """
    response = await client.post(
        "/prov/events", json={**DATA_DISCLOSED, "consent_snapshot_hash": value}
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_disclosure_is_linked_to_the_dataset_its_hash_is_over(client):
    """Otherwise the disclosure hangs off the recipient alone, and the lineage
    graph an auditor traverses never connects the handover to the data product.
    """
    await client.post("/prov/events", json=DATA_DISCLOSED)

    entities = await client.get("/prov/entities")
    entity_ids = [n["@id"] for n in entities.json()["@graph"]]
    assert DATA_DISCLOSED["dataset_id"] in entity_ids


@pytest.mark.asyncio
async def test_data_ingested_generates_dataset_entity(client):
    await client.post("/prov/events", json=DATA_INGESTED)

    entities = await client.get("/prov/entities")
    entity_ids = [n["@id"] for n in entities.json()["@graph"]]
    assert DATA_INGESTED["dataset_id"] in entity_ids


@pytest.mark.asyncio
async def test_consent_granted_is_idempotent(client):
    r1 = await client.post("/prov/events", json=CONSENT_GRANTED)
    assert r1.status_code == 201
    r2 = await client.post("/prov/events", json=CONSENT_GRANTED)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_new_events_queryable_by_type(client):
    await client.post("/prov/events", json=DATA_INGESTED)
    response = await client.get("/prov/events?event_type=DataIngested")
    assert response.status_code == 200
    graph = response.json()["@graph"]
    assert len(graph) >= 1
    # data_product_id column is populated from dataset_id for these events
    assert any(
        e.get("ds:dataProductId") == DATA_INGESTED["dataset_id"] for e in graph
    )
