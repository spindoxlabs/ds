"""Tests for /internal endpoints."""
import pytest
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from connector.services.agreement_service import upsert_agreement
from connector.services.consent_service import create_consent_request


@pytest.mark.asyncio
async def test_agreement_status_not_found(client):
    r = await client.get("/internal/agreements/nonexistent/status")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_agreement_status_found(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await upsert_agreement(
                session,
                agreement_id="urn:uuid:test-agreement-001",
                asset_id="https://provider.example/datasets/meters",
                consumer_id="consumer",
                provider_id="provider",
                policy_snapshot={"@type": "odrl:Set"},
                agreed_at=datetime.now(timezone.utc),
            )

    r = await client.get("/internal/agreements/urn:uuid:test-agreement-001/status")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["asset_id"] == "https://provider.example/datasets/meters"
    assert body["consumer_id"] == "consumer"


@pytest.mark.asyncio
async def test_consent_check_no_consent(client):
    r = await client.get("/internal/consent/check", params={
        "subject_id": "sub-001",
        "dataset_id": "datasets.silver.meters",
        "consumer_id": "consumer",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["consent_active"] is False


@pytest.mark.asyncio
async def test_consent_check_uses_latest_status(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add_all([
                ConsentRequestORM(
                    subject_id="sub-001",
                    dataset_id="datasets.silver.meters",
                    consumer_id="consumer",
                    status="granted",
                    requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
                ConsentRequestORM(
                    subject_id="sub-001",
                    dataset_id="datasets.silver.meters",
                    consumer_id="consumer",
                    status="revoked",
                    requested_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    decided_at=datetime(2026, 1, 2, 1, tzinfo=timezone.utc),
                    revoked_at=datetime(2026, 1, 2, 2, tzinfo=timezone.utc),
                    purpose=[],
                    transfer_ids=[],
                ),
            ])

    r = await client.get("/internal/consent/check", params={
        "subject_id": "sub-001",
        "dataset_id": "datasets.silver.meters",
        "consumer_id": "consumer",
    })
    assert r.status_code == 200
    assert r.json()["consent_active"] is False

    r = await client.get("/internal/consent/check", params={
        "dataset_id": "datasets.silver.meters",
        "consumer_id": "consumer",
    })
    assert r.status_code == 200
    assert r.json()["subject_ids"] == []


@pytest.mark.asyncio
async def test_create_consent_request_reuses_open_request(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            first = await create_consent_request(
                session,
                subject_id="sub-001",
                dataset_id="datasets.silver.meters",
                consumer_id="consumer",
            )
            second = await create_consent_request(
                session,
                subject_id="sub-001",
                dataset_id="datasets.silver.meters",
                consumer_id="consumer",
            )

        result = await session.execute(select(func.count()).select_from(ConsentRequestORM))

    assert second.id == first.id
    assert result.scalar_one() == 1
