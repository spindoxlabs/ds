"""Tests for organization membership API."""

from __future__ import annotations

import pytest
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


SUBJECT_DID = "did:web:rec.dataspaces.localhost:users:data-subject"
CONSUMER_DID = "did:web:third-party.dataspaces.localhost:users:consumer-user"
ORG_ALIAS = "example-org"


class TestMembershipCRUD:
    @pytest.mark.asyncio
    async def test_create_membership(self, client, admin_headers):
        await _create_did(client, SUBJECT_DID, admin_headers)
        resp = await client.post(
            "/admin/memberships",
            json={
                "user_did": SUBJECT_DID,
                "organization_alias": ORG_ALIAS,
                # Still sent, deliberately: a caller written before migration
                # 0017 must not start failing. The field is ignored, which is
                # what it amounted to before — the column was written and read
                # by nothing.
                "role": "consumer",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_did"] == SUBJECT_DID
        assert data["organization_alias"] == ORG_ALIAS
        assert data["status"] == "active"
        # What somebody *is* in their community is a `communityRole` claim on
        # their credential (`D-54`), not a membership field.
        assert "role" not in data

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
                "user_did": "did:web:rec.dataspaces.localhost:users:never-registered",
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


class TestOneOrganisationIsOneMembership:
    """An organisation answers to several names; it must not gain several members.

    ``Owner.aliases`` exists because a realm, a governance file and an owner list
    routinely spell one organisation differently, and ``/owners/resolve`` has
    always collapsed them. This table used to compare ``organization_alias`` as a
    literal string on every route, so the spellings behaved as different
    organisations: a row written under an alias was invisible to a check made
    under the owner id, and a member holding an active membership was refused.
    """

    OWNER = {
        "id": "example-org",
        "type": "schema:NGO",
        "name": "Example Organization",
        "did": "did:web:rec.dataspaces.localhost",
        "aliases": ["example", "ex-org"],
    }

    async def _owner(self, client, admin_headers):
        await client.post("/admin/owners", json=self.OWNER, headers=admin_headers)

    @pytest.mark.asyncio
    async def test_a_membership_written_by_alias_is_stored_under_the_owner_id(
        self, client, admin_headers
    ):
        await self._owner(client, admin_headers)
        await _create_did(client, SUBJECT_DID, admin_headers)

        resp = await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "ex-org"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["organization_alias"] == "example-org"

    @pytest.mark.asyncio
    async def test_a_check_by_any_spelling_finds_the_same_member(
        self, client, admin_headers, membership_headers
    ):
        await self._owner(client, admin_headers)
        await _create_did(client, SUBJECT_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "ex-org"},
            headers=admin_headers,
        )

        for spelling in ("example-org", "example", "ex-org"):
            resp = await client.get(
                "/memberships/check",
                params={"user_did": SUBJECT_DID, "organization": spelling},
                headers=membership_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["member"] is True, spelling

    @pytest.mark.asyncio
    async def test_a_second_spelling_cannot_create_a_second_membership(
        self, client, admin_headers
    ):
        """Two names, one row — otherwise revocation removes only one of them."""
        await self._owner(client, admin_headers)
        await _create_did(client, SUBJECT_DID, admin_headers)

        first = await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "example-org"},
            headers=admin_headers,
        )
        assert first.status_code == 201
        second = await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "ex-org"},
            headers=admin_headers,
        )
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_a_delete_by_alias_removes_the_row_its_create_wrote(
        self, client, admin_headers, membership_headers
    ):
        """The orphan case: a delete that resolved differently left the row behind.

        Revocation believed it had removed the membership, and the check the
        connector makes still found one.
        """
        await self._owner(client, admin_headers)
        await _create_did(client, SUBJECT_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "example-org"},
            headers=admin_headers,
        )

        resp = await client.delete(
            f"/admin/memberships/{SUBJECT_DID}/ex-org", headers=admin_headers
        )
        assert resp.status_code == 204

        check = await client.get(
            "/memberships/check",
            params={"user_did": SUBJECT_DID, "organization": "example-org"},
            headers=membership_headers,
        )
        assert check.json()["member"] is False

    @pytest.mark.asyncio
    async def test_a_list_filtered_by_alias_returns_the_same_members(
        self, client, admin_headers
    ):
        await self._owner(client, admin_headers)
        await _create_did(client, SUBJECT_DID, admin_headers)
        await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "example-org"},
            headers=admin_headers,
        )

        by_alias = await client.get(
            "/admin/memberships",
            params={"organization": "ex-org"},
            headers=admin_headers,
        )
        assert [m["user_did"] for m in by_alias.json()] == [SUBJECT_DID]

    @pytest.mark.asyncio
    async def test_a_name_that_owns_nothing_is_stored_verbatim(
        self, client, admin_headers
    ):
        """A deployment that registers no owners keeps working exactly as before.

        Resolution must not turn an unregistered organisation into a 404 — the
        literal-string behaviour is the fallback, not an error.
        """
        await _create_did(client, SUBJECT_DID, admin_headers)
        resp = await client.post(
            "/admin/memberships",
            json={"user_did": SUBJECT_DID, "organization_alias": "no-such-owner"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["organization_alias"] == "no-such-owner"
