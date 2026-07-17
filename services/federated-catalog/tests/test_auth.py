"""Tests for JWT scope enforcement on federated-catalog endpoints."""
import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from federated_catalog.cache import CatalogCache
from federated_catalog.config import get_settings
from federated_catalog.main import create_app


def make_headers(scope: str = "catalog.read") -> dict:
    token = pyjwt.encode({"scope": scope, "sub": "test"}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def client():
    app = create_app()
    app.state.cache = CatalogCache()
    app.state.settings = get_settings()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_no_auth(client):
    r = await client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_catalog_without_token_returns_401(client):
    r = await client.get("/catalog")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_catalog_wrong_scope_returns_403(client):
    r = await client.get(
        "/catalog",
        headers=make_headers(scope="some.other.scope"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_catalog_with_correct_scope(client):
    r = await client.get(
        "/catalog",
        headers=make_headers(scope="catalog.read"),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_catalog_context_requires_auth(client):
    r = await client.get("/catalog/context")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_catalog_search_requires_auth(client):
    r = await client.post("/catalog/search", json={"q": "test"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_catalog_search_with_scope(client):
    r = await client.post(
        "/catalog/search",
        json={"q": "test"},
        headers=make_headers(scope="catalog.read"),
    )
    assert r.status_code == 200
