"""Tests for GET /provider/authorizations."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM


@pytest.mark.asyncio
async def test_authorizations_empty(client):
    r = await client.get("/provider/authorizations")
    assert r.status_code == 200
    assert r.json() == {"datasets": []}


@pytest.mark.asyncio
async def test_authorizations_returns_granted(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add_all([
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:alice",
                    dataset_id="datasets.silver.meters_15m",
                    consumer_id="did:web:tp.ds.localhost",
                    status="granted",
                    requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:bob",
                    dataset_id="datasets.silver.meters_15m",
                    consumer_id="did:web:tp.ds.localhost",
                    status="granted",
                    requested_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 2, 1, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
            ])

    r = await client.get("/provider/authorizations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["datasets"]) == 1
    ds = body["datasets"][0]
    assert ds["dataset_id"] == "datasets.silver.meters_15m"
    assert sorted(ds["consented_subjects"]) == [
        "did:web:users.ds.localhost:alice",
        "did:web:users.ds.localhost:bob",
    ]
    assert "updated_at" in ds


@pytest.mark.asyncio
async def test_authorizations_excludes_revoked(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add_all([
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:alice",
                    dataset_id="datasets.silver.meters_15m",
                    consumer_id="did:web:tp.ds.localhost",
                    status="granted",
                    requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:alice",
                    dataset_id="datasets.silver.meters_15m",
                    consumer_id="did:web:tp.ds.localhost",
                    status="revoked",
                    requested_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 2, 1, tzinfo=timezone.utc),
                    revoked_at=datetime(2026, 1, 2, 2, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
            ])

    r = await client.get("/provider/authorizations")
    assert r.status_code == 200
    assert r.json() == {"datasets": []}


@pytest.mark.asyncio
async def test_authorizations_multiple_datasets(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add_all([
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:alice",
                    dataset_id="datasets.silver.meters_15m",
                    consumer_id="did:web:tp.ds.localhost",
                    status="granted",
                    requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:bob",
                    dataset_id="datasets.gold.energy_community",
                    consumer_id="did:web:tp.ds.localhost",
                    status="granted",
                    requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
            ])

    r = await client.get("/provider/authorizations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["datasets"]) == 2
    ids = [d["dataset_id"] for d in body["datasets"]]
    assert "datasets.gold.energy_community" in ids
    assert "datasets.silver.meters_15m" in ids


@pytest.mark.asyncio
async def test_authorizations_no_private_data(engine, client):
    """Ensure the response contains no private data (consumer IDs, purposes, messages)."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add(
                ConsentRequestORM(
                    subject_id="did:web:users.ds.localhost:alice",
                    dataset_id="datasets.silver.meters_15m",
                    consumer_id="did:web:tp.ds.localhost",
                    status="granted",
                    requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                    purpose=["analytics"],
                    message="Please share data",
                    notification_url="http://internal.example/webhook",
                    transfer_ids=["tx-001"],
                ),
            )

    r = await client.get("/provider/authorizations")
    assert r.status_code == 200
    body = r.json()

    response_text = str(body)
    assert "did:web:tp.ds.localhost" not in response_text
    assert "analytics" not in response_text
    assert "Please share data" not in response_text
    assert "internal.example" not in response_text
    assert "tx-001" not in response_text
