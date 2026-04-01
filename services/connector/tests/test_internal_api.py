"""Tests for /internal endpoints."""
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ds.connector.db.engine import Base
from ds.connector.services.agreement_service import upsert_agreement


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
