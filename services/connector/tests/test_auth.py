"""Tests for JWT scope enforcement on connector endpoints."""

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.config import get_settings
from connector.db.engine import Base
from connector.dependencies import get_db, get_participant_registry
from connector.main import create_app
from connector.registry.participants import ParticipantRegistry
from tests import make_headers

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

EDC = get_settings().edc_rec_management_url.rstrip("/")


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
    app.dependency_overrides[get_participant_registry] = lambda: (
        ParticipantRegistry.empty()
    )

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


@pytest.mark.rule("C-17", "X-4")
@pytest.mark.asyncio
async def test_internal_without_token_returns_401(auth_client):
    r = await auth_client.get("/internal/agreements/test/status")
    assert r.status_code == 401


@pytest.mark.rule("C-17", "X-4")
@pytest.mark.asyncio
async def test_internal_wrong_scope_returns_403(auth_client):
    r = await auth_client.get(
        "/internal/agreements/test/status",
        headers=make_headers(scope="connector.admin"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
@respx.mock
async def test_internal_with_correct_scope(auth_client):
    """The right scope gets past the guard — whatever the EDC then says.

    The EDC is mocked because this is an *authorization* test and must not
    depend on one. Unmocked it reached the real management API, so its result
    tracked whether a stack happened to be running: a live EDC answers 404 for
    an unknown agreement, an absent one raises `EdcUnreachable` and the route
    503s (`CON-04`). Both are correct route behaviour and neither is what this
    test is about, so it asserted 404 and went red exactly when nobody had the
    stack up. The outcomes themselves are pinned in `test_internal_api.py`.
    """
    respx.get(f"{EDC}/v3/contractagreements/test").mock(
        return_value=httpx.Response(404)
    )
    r = await auth_client.get(
        "/internal/agreements/test/status",
        headers=make_headers(scope="connector.internal"),
    )
    assert r.status_code not in (401, 403)
    assert r.status_code == 404


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_consent_check_requires_scope(auth_client):
    r = await auth_client.get(
        "/internal/consent/check",
        params={
            "dataset_id": "ds",
            "consumer_id": "c",
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_audit_query_requires_scope(auth_client):
    r = await auth_client.post("/internal/audit/query", json={"dataset_id": "ds"})
    assert r.status_code == 401


# ── /admin/participants requires connector.provider.read ─────────
#
# Not `connector.admin`, which this section used to claim. Admin satisfies it as
# a superset, so asserting only with an admin token left the requirement the
# route actually declares — the weaker one — untested.


@pytest.mark.rule("C-17")
@pytest.mark.asyncio
async def test_admin_without_token_returns_401(auth_client):
    r = await auth_client.get("/admin/participants")
    assert r.status_code == 401


@pytest.mark.rule("C-17")
@pytest.mark.asyncio
async def test_admin_wrong_scope_returns_403(auth_client):
    r = await auth_client.get(
        "/admin/participants",
        headers=make_headers(scope="connector.internal"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_with_provider_read_scope(auth_client):
    """The requirement as declared: `require_provider_read`."""
    r = await auth_client.get(
        "/admin/participants",
        headers=make_headers(scope="connector.provider.read"),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_admin_with_admin_scope_as_superset(auth_client):
    r = await auth_client.get(
        "/admin/participants",
        headers=make_headers(scope="connector.admin"),
    )
    assert r.status_code == 200


# ── /metrics is unauthenticated, deliberately ────────────────────
#
# Reachability is a deployment control: under Helm a default-deny NetworkPolicy
# makes the port reachable by nothing, and `global.monitoring.serviceMonitor`
# opens it to the Prometheus namespace alone — never through an Ingress. An
# app-layer guard would break a scraper, which holds no Keycloak token.
# Asserted so a future change has to argue with this comment first.


@pytest.mark.asyncio
async def test_metrics_is_deliberately_open(auth_client):
    r = await auth_client.get("/metrics")
    assert r.status_code == 200
    assert "ds_service_up" in r.text


# ── Webhook endpoints require connector.webhook ──────────────────


@pytest.mark.rule("C-17")
@pytest.mark.asyncio
async def test_webhook_without_token_returns_401(auth_client):
    r = await auth_client.post(
        "/webhooks/transfer-process",
        json={
            "type": "test",
            "transferId": "t-1",
        },
    )
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
