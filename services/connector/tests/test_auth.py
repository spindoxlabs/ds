"""Tests for JWT scope enforcement on connector endpoints."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.db.engine import Base
from connector.dependencies import get_db, get_participant_registry
from connector.main import create_app
from connector.registry.participants import ParticipantRegistry

from tests import make_headers

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def auth_client():
    """Client with participant registry mocked (admin endpoint needs it)."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(eng, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_participant_registry] = lambda: ParticipantRegistry.empty()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.mark.asyncio
async def test_health_no_auth(auth_client):
    r = await auth_client.get("/health")
    assert r.status_code == 200


# ── Internal endpoints require connector.internal ────────────────

@pytest.mark.asyncio
async def test_internal_without_token_returns_401(auth_client):
    r = await auth_client.get("/internal/agreements/test/status")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_internal_wrong_scope_returns_403(auth_client):
    r = await auth_client.get(
        "/internal/agreements/test/status",
        headers=make_headers(scope="connector.admin"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_internal_with_correct_scope(auth_client):
    r = await auth_client.get(
        "/internal/agreements/test/status",
        headers=make_headers(scope="connector.internal"),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_consent_check_requires_scope(auth_client):
    r = await auth_client.get("/internal/consent/check", params={
        "dataset_id": "ds", "consumer_id": "c",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_audit_query_requires_scope(auth_client):
    r = await auth_client.post("/internal/audit/query", json={"dataset_id": "ds"})
    assert r.status_code == 401


# ── Admin endpoints require connector.admin ──────────────────────

@pytest.mark.asyncio
async def test_admin_without_token_returns_401(auth_client):
    r = await auth_client.get("/admin/participants")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_wrong_scope_returns_403(auth_client):
    r = await auth_client.get(
        "/admin/participants",
        headers=make_headers(scope="connector.internal"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_with_correct_scope(auth_client):
    r = await auth_client.get(
        "/admin/participants",
        headers=make_headers(scope="connector.admin"),
    )
    assert r.status_code == 200


# ── Webhook endpoints require connector.webhook ──────────────────

@pytest.mark.asyncio
async def test_webhook_without_token_returns_401(auth_client):
    r = await auth_client.post("/webhooks/transfer-process", json={
        "type": "test", "transferId": "t-1",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhook_wrong_scope_returns_403(auth_client):
    r = await auth_client.post(
        "/webhooks/transfer-process",
        json={"type": "test", "transferId": "t-1"},
        headers=make_headers(scope="connector.admin"),
    )
    assert r.status_code == 403


# ── Consent register-transfer requires connector.internal ────────

@pytest.mark.asyncio
async def test_consent_register_transfer_requires_scope(auth_client):
    r = await auth_client.post(
        "/consent/register-transfer",
        json={"consent_request_id": 1, "transfer_id": "t-1"},
    )
    assert r.status_code == 401
