"""Route-declaration order, which is behaviour here and not style.

`GET /catalog/{dataset_iri:path}` is a catch-all. Anything mounted under
`/catalog` that it is declared *before* becomes unreachable by that name, and the
symptom is never a routing error — it is a 404 saying the dataset was not found,
or a 401 from the guard on a dataset lookup. Both read as something else.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from federated_catalog.cache import CatalogCache
from federated_catalog.config import get_settings
from federated_catalog.main import create_app

from .test_auth import make_headers


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
async def test_context_is_not_eaten_by_the_dataset_catch_all(client):
    """`/catalog/context` must resolve to its own handler, not to a dataset lookup.

    It is mounted on a router included *before* the guarded one. Reverse the two
    includes and this returns 401 — the guard on `GET /catalog/{iri}` — which
    looks like a permissions problem and is a routing one.
    """
    r = await client.get("/catalog/context")
    assert r.status_code == 200
    assert "@context" in r.json()


@pytest.mark.asyncio
async def test_meta_is_not_eaten_by_the_dataset_catch_all(client):
    r = await client.get("/catalog/meta", headers=make_headers())
    assert r.status_code == 200
    assert "dataset_count" in r.json()


@pytest.mark.asyncio
async def test_search_resolves_to_search_not_the_catch_all(client):
    """`POST /catalog/search` is **not** shadowed, contrary to the plan's row.

    The catch-all is `GET`-only, and Starlette records a method mismatch as a
    partial match and keeps scanning — so the `POST` route later in the table
    still wins. The row asked for a reordering that would have changed nothing;
    this test is what says so, and what would notice if the catch-all ever gained
    a `POST`.
    """
    r = await client.post(
        "/catalog/search", json={"q": "anything"}, headers=make_headers()
    )
    assert r.status_code == 200
    assert r.json()["@type"] == "dcat:Catalog"


@pytest.mark.asyncio
async def test_a_real_dataset_iri_still_reaches_the_catch_all(client):
    r = await client.get("/catalog/datasets.silver.meters_15m", headers=make_headers())
    assert r.status_code == 404
    assert "not found in catalog" in r.json()["detail"]
