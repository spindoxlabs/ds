"""Tests for owner CRUD API and alias resolution."""
from __future__ import annotations

import pytest
import pytest_asyncio

from conftest import make_headers


@pytest.fixture
def admin_headers():
    return make_headers("identity-registry.admin")


@pytest.fixture
def read_headers():
    return make_headers("identity-registry.read")


EXAMPLE_OWNER = {
    "id": "example-org",
    "type": "schema:NGO",
    "name": "Example Organization",
    "did": "did:web:provider.dataspaces.localhost",
    "aliases": ["example", "ex-org"],
}


class TestOwnerCRUD:
    @pytest.mark.asyncio
    async def test_create_owner(self, client, admin_headers):
        resp = await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "example-org"
        assert data["name"] == "Example Organization"
        assert data["type"] == "schema:NGO"
        assert data["did"] == "did:web:provider.dataspaces.localhost"
        assert data["aliases"] == ["example", "ex-org"]
        assert data["canonical_uri"] == "did:web:provider.dataspaces.localhost"

    @pytest.mark.asyncio
    async def test_create_duplicate_owner(self, client, admin_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_owners(self, client, admin_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.get("/admin/owners", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "example-org"

    @pytest.mark.asyncio
    async def test_get_owner(self, client, admin_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.get(
            "/admin/owners/example-org", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == "example-org"

    @pytest.mark.asyncio
    async def test_get_owner_not_found(self, client, admin_headers):
        resp = await client.get(
            "/admin/owners/nonexistent", headers=admin_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_owner(self, client, admin_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.put(
            "/admin/owners/example-org",
            json={"name": "Updated Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"
        assert resp.json()["type"] == "schema:NGO"

    @pytest.mark.asyncio
    async def test_update_owner_not_found(self, client, admin_headers):
        resp = await client.put(
            "/admin/owners/nonexistent",
            json={"name": "Whatever"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_owner(self, client, admin_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.delete(
            "/admin/owners/example-org", headers=admin_headers
        )
        assert resp.status_code == 204

        resp = await client.get(
            "/admin/owners/example-org", headers=admin_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_owner_not_found(self, client, admin_headers):
        resp = await client.delete(
            "/admin/owners/nonexistent", headers=admin_headers
        )
        assert resp.status_code == 404


class TestOwnerResolve:
    @pytest.mark.asyncio
    async def test_resolve_by_id(self, client, admin_headers, read_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.get(
            "/owners/resolve",
            params={"alias": "example-org"},
            headers=read_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == "example-org"
        assert resp.json()["canonical_uri"] == "did:web:provider.dataspaces.localhost"

    @pytest.mark.asyncio
    async def test_resolve_by_alias(self, client, admin_headers, read_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.get(
            "/owners/resolve",
            params={"alias": "example"},
            headers=read_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == "example-org"

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, client, read_headers):
        resp = await client.get(
            "/owners/resolve",
            params={"alias": "nonexistent"},
            headers=read_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resolve_canonical_uri_url_fallback(self, client, admin_headers, read_headers):
        owner = {
            "id": "open-data-provider",
            "name": "Open Data Provider",
            "url": "https://open-data.example.org",
        }
        await client.post("/admin/owners", json=owner, headers=admin_headers)
        resp = await client.get(
            "/owners/resolve",
            params={"alias": "open-data-provider"},
            headers=read_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["canonical_uri"] == "https://open-data.example.org"


class TestOwnerAuth:
    @pytest.mark.asyncio
    async def test_admin_endpoints_require_admin_scope(self, client):
        read_headers = make_headers("identity-registry.read")
        resp = await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=read_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_resolve_requires_read_scope(self, client):
        resp = await client.get(
            "/owners/resolve", params={"alias": "test"}
        )
        assert resp.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_resolve_works_with_admin_scope(self, client, admin_headers):
        await client.post(
            "/admin/owners", json=EXAMPLE_OWNER, headers=admin_headers
        )
        resp = await client.get(
            "/owners/resolve",
            params={"alias": "example-org"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
