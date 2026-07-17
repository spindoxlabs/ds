"""Tests for JWT scope enforcement on provenance endpoints."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import make_headers
from provenance.db.engine import Base
from provenance.dependencies import get_db
from provenance.main import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def raw_client():
    """Client WITHOUT default auth headers for testing 401/403."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(eng, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.mark.asyncio
async def test_health_no_auth(raw_client):
    r = await raw_client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_context_no_auth(raw_client):
    r = await raw_client.get("/prov/context")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_write_without_token_returns_401(raw_client):
    r = await raw_client.post("/prov/events", json={
        "type": "CataloguePublished",
        "provider_id": "p",
        "catalogue_id": "c",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_read_without_token_returns_401(raw_client):
    r = await raw_client.get("/prov/lineage/urn:test")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_audit_without_token_returns_401(raw_client):
    r = await raw_client.get("/audit/log")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_write_with_read_scope_returns_403(raw_client):
    r = await raw_client.post(
        "/prov/relations",
        json={"subject": "a", "predicate": "wasAttributedTo", "object": "b"},
        headers=make_headers(scope="provenance.read"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_read_with_read_scope_ok(raw_client):
    r = await raw_client.get(
        "/prov/entities",
        headers=make_headers(scope="provenance.read"),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_write_with_write_scope_ok(raw_client):
    r = await raw_client.post(
        "/prov/entities",
        json={"iri": "urn:test:entity", "type": "prov:Entity"},
        headers=make_headers(scope="provenance.write"),
    )
    assert r.status_code == 201
