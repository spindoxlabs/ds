"""Tests for organization membership API."""
from __future__ import annotations

import pytest
import pytest_asyncio

from conftest import make_headers


@pytest.fixture
def admin_headers():
    return make_headers("identity-registry.admin")


@pytest.fixture
def membership_headers():
    return make_headers("identity-registry.membership.read")


async def _create_did(client, did: str, admin_headers: dict):
    """Helper: create a DID so we can reference it in memberships."""
    await client.post(
        "/admin/dids",
        json={"did": did, "did_type": "user"},
        headers=admin_headers,
    )


SUBJECT_DID = "did:web:users.dataspaces.localhost:data-subject"
CONSUMER_DID = "did:web:users.dataspaces.localhost:consumer-user"
ORG_ALIAS = "example-org"


class TestMembershipCRUD:
    @pytest.mark.asyncio
    async def test_create_membership(self, client, admin_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        resp = await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS, "role": "consumer"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_did"] == SUBJECT_DID
        assert data["organization_alias"] == ORG_ALIAS
        assert data["role"] == "consumer"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_duplicate_membership(self, client, admin_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        body = {"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS}
        await client.post("/admin/memberships", json=body, headers=admin_headers)
        resp = await client.post("/admin/memberships", json=body, headers=admin_headers)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_membership_unknown_did(self, client, admin_headers):
        """An unregistered DID must return 404, not a FK IntegrityError as a 500."""
        resp = await client.post(
            "/admin/memberships",
            json={
                "user_did": "did:web:users.dataspaces.localhost:never-registered",
                "organization_alias": ORG_ALIAS,
                "role": "member",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 404
        assert "never-registered" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_by_organization(self, client, admin_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        await _create_did(client, CONSUMER_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS},
            headers=admin_headers,
        )
        await client.post(
            "/admin/memberships",
            json={"user_did": CONSUMER_DID, "organization_alias": ORG_ALIAS},
            headers=admin_headers,
        )
        resp = await client.get(
            "/admin/memberships",
            params={"organization": ORG_ALIAS},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_by_user(self, client, admin_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS},
            headers=admin_headers,
        )
        resp = await client.get(
            "/admin/memberships",
            params={"user_did": SUBJECT_DID},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_delete_membership(self, client, admin_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS},
            headers=admin_headers,
        )
        resp = await client.delete(
            f"/admin/memberships/{SUBJECT_DID}/{ORG_ALIAS}",
            headers=admin_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client, admin_headers):
        resp = await client.delete(
            f"/admin/memberships/{SUBJECT_DID}/nonexistent",
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestMembershipCheck:
    @pytest.mark.asyncio
    async def test_check_active_member(self, client, admin_headers, membership_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS},
            headers=admin_headers,
        )
        resp = await client.get(
            "/memberships/check",
            params={"user_did": SUBJECT_DID, "organization": ORG_ALIAS},
            headers=membership_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["member"] is True

    @pytest.mark.asyncio
    async def test_check_non_member(self, client, membership_headers):
        resp = await client.get(
            "/memberships/check",
            params={"user_did": SUBJECT_DID, "organization": ORG_ALIAS},
            headers=membership_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["member"] is False

    @pytest.mark.asyncio
    async def test_check_works_with_admin_scope(self, client, admin_headers):
        resp = await client.get(
            "/memberships/check",
            params={"user_did": SUBJECT_DID, "organization": ORG_ALIAS},
            headers=admin_headers,
        )
        assert resp.status_code == 200


class TestMembershipAuth:
    @pytest.mark.asyncio
    async def test_admin_endpoints_require_admin(self, client, membership_headers):
        resp = await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": ORG_ALIAS},
            headers=membership_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_check_requires_membership_read(self, client):
        read_headers = make_headers("identity-registry.read")
        resp = await client.get(
            "/memberships/check",
            params={"user_did": SUBJECT_DID, "organization": ORG_ALIAS},
            headers=read_headers,
        )
        assert resp.status_code == 403
