"""Tests for JWT scope enforcement on federated-catalog endpoints."""
import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from federated_catalog.cache import CatalogCache
from federated_catalog.config import get_settings
from federated_catalog.main import create_app

from . import SIGNING_KEY


def make_headers(scope: str = "catalog.read") -> dict:
    """A **service-account** token, which is what actually calls this service.

    The claims matter. `{scope, sub}` alone — what this helper minted before —
    is not a token Keycloak issues: a client-credentials grant always carries
    `azp`, `client_id` and `preferred_username: service-account-<client>`, and
    without any of them `ds_auth.is_service_account` correctly reads the token as
    a *user*. A user is authorized by expanded groups, this one has none, so both
    "correct scope" cases got 403 and the suite recorded two permanent failures
    against code that was behaving exactly as designed.

    The plan blames `ds-auth` for this and that is wrong — see the correction in
    the ledger. Teaching `is_service_account` that a bare `scope` claim means a
    service would classify **every user token** as a service account, because
    Keycloak puts `scope` on those too (`openid profile email`). That trades two
    red tests for a collapsed authorization model.
    """
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "test",
            "azp": "svc-ds-federated-catalog",
            "client_id": "svc-ds-federated-catalog",
            "preferred_username": "service-account-svc-ds-federated-catalog",
        },
        SIGNING_KEY,
        algorithm="HS256",
    )
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
async def test_catalog_context_is_public(client):
    """The JSON-LD context is dereferenceable without a token.

    Every document this service returns advertises it as its `@context`, so a
    JSON-LD processor fetches it as a matter of course — holding no credential,
    because it is a parser and not a participant. Guarding it made our own
    documents unprocessable while protecting a fixed list of vocabulary
    prefixes that discloses no dataset, participant or offer.
    """
    r = await client.get("/catalog/context")
    assert r.status_code == 200
    assert "dcat" in r.json()["@context"]


@pytest.mark.asyncio
async def test_catalog_meta_still_requires_auth(client):
    """The sibling route is unaffected — only `/context` left the guard."""
    r = await client.get("/catalog/meta")
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
