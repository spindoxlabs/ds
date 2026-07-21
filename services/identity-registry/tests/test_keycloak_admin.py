"""Tests for the Keycloak Admin client and organization sync.

The KC Admin REST API is faked with an httpx MockTransport backed by a small
in-memory realm, so idempotency is asserted by running the sync twice against
the same state.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from identity_registry.services.keycloak_admin import (
    KeycloakAdminClient,
    OrganizationsConfig,
    load_organizations_config,
    sync_organizations,
)

REALM = "dataspaces"
BASE_URL = "http://kc.test"


class FakeKeycloak:
    """Minimal in-memory stand-in for the KC Admin REST API."""

    def __init__(self, users: dict[str, str] | None = None):
        # email -> user uuid
        self.users = users or {}
        self.orgs: list[dict] = []
        self.org_groups: dict[str, list[dict]] = {}
        self.org_members: dict[str, list[dict]] = {}
        self.group_members: set[tuple[str, str, str]] = set()
        self.requests: list[tuple[str, str]] = []
        self._next_id = 0

    def _mint_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        self.requests.append((method, path))

        if path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "fake-token"})

        prefix = f"/admin/realms/{REALM}"
        assert path.startswith(prefix), path
        sub = path[len(prefix) :]

        if sub == "/users" and method == "GET":
            email = request.url.params.get("email")
            uid = self.users.get(email)
            found = [{"id": uid, "email": email}] if uid else []
            return httpx.Response(200, json=found)

        if sub == "/organizations" and method == "GET":
            return httpx.Response(200, json=self.orgs)

        if sub == "/organizations" and method == "POST":
            body = json.loads(request.content)
            if any(o["alias"] == body["alias"] for o in self.orgs):
                return httpx.Response(409)
            org = {"id": self._mint_id("org"), **body}
            self.orgs.append(org)
            self.org_groups[org["id"]] = []
            self.org_members[org["id"]] = []
            return httpx.Response(201)

        parts = sub.strip("/").split("/")
        # organizations/{org_id}/...
        if len(parts) >= 3 and parts[0] == "organizations":
            org_id = parts[1]
            tail = parts[2:]

            if tail == ["members"] and method == "GET":
                return httpx.Response(200, json=self.org_members.get(org_id, []))

            if tail == ["members"] and method == "POST":
                user_id = request.content.decode()
                members = self.org_members.setdefault(org_id, [])
                if any(m["id"] == user_id for m in members):
                    return httpx.Response(409)
                members.append({"id": user_id})
                return httpx.Response(201)

            if tail == ["groups"] and method == "GET":
                return httpx.Response(200, json=self.org_groups.get(org_id, []))

            if tail == ["groups"] and method == "POST":
                body = json.loads(request.content)
                groups = self.org_groups.setdefault(org_id, [])
                if any(g["name"] == body["name"] for g in groups):
                    return httpx.Response(409)
                groups.append({"id": self._mint_id("grp"), "name": body["name"]})
                return httpx.Response(201)

            # groups/{group_id}/members/{user_id}
            if len(tail) == 4 and tail[0] == "groups" and tail[2] == "members":
                self.group_members.add((org_id, tail[1], tail[3]))
                return httpx.Response(204)

        return httpx.Response(404)


async def make_client(fake: FakeKeycloak) -> KeycloakAdminClient:
    transport = httpx.MockTransport(fake.handler)
    client = httpx.AsyncClient(transport=transport)
    return await KeycloakAdminClient.authenticate(
        BASE_URL, REALM, admin_user="admin", admin_password="admin", client=client
    )


CONFIG = OrganizationsConfig.model_validate(
    {
        "realm": REALM,
        "organizations": [
            {
                "alias": "example-org",
                "name": "Example Organization",
                "attributes": {"type": ["dso"]},
                "members": [
                    {"email": "provider@example.test", "groups": ["dataset.admin"]},
                    {"email": "consumer@example.test", "groups": ["consumer"]},
                ],
            }
        ],
    }
)

USERS = {
    "provider@example.test": "user-provider",
    "consumer@example.test": "user-consumer",
}


class TestLoadConfig:
    def test_parses_full_config(self, tmp_path: Path):
        path = tmp_path / "organizations.yaml"
        path.write_text(
            "realm: dataspaces\n"
            "organizations:\n"
            "  - alias: example-org\n"
            "    name: Example Organization\n"
            "    domains: []\n"
            "    attributes:\n"
            "      type: [\"dso\"]\n"
            "    members:\n"
            "      - email: provider@example.test\n"
            "        groups: [dataset.admin]\n"
        )
        config = load_organizations_config(path)
        assert config.realm == "dataspaces"
        assert len(config.organizations) == 1
        org = config.organizations[0]
        assert org.alias == "example-org"
        assert org.attributes == {"type": ["dso"]}
        assert org.members[0].email == "provider@example.test"
        assert org.members[0].groups == ["dataset.admin"]

    def test_empty_file_yields_no_organizations(self, tmp_path: Path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        assert load_organizations_config(path).organizations == []

    def test_display_name_falls_back_to_alias(self):
        config = OrganizationsConfig.model_validate(
            {"organizations": [{"alias": "solo-org"}]}
        )
        assert config.organizations[0].display_name == "solo-org"

    def test_members_default_to_no_groups(self):
        config = OrganizationsConfig.model_validate(
            {"organizations": [{"alias": "o", "members": [{"email": "a@b.test"}]}]}
        )
        assert config.organizations[0].members[0].groups == []


class TestSyncOrganizations:
    @pytest.mark.asyncio
    async def test_creates_org_members_and_groups(self):
        fake = FakeKeycloak(USERS)
        kc = await make_client(fake)
        report = await sync_organizations(CONFIG, kc)

        assert report.organizations_created == ["example-org"]
        assert report.organizations_existing == []
        assert sorted(report.members_added) == [
            "example-org/consumer@example.test",
            "example-org/provider@example.test",
        ]
        assert sorted(report.groups_assigned) == [
            "example-org/consumer@example.test/consumer",
            "example-org/provider@example.test/dataset.admin",
        ]
        assert report.missing_users == []
        assert not report.has_warnings

        org = fake.orgs[0]
        assert org["alias"] == "example-org"
        assert org["name"] == "Example Organization"
        assert org["attributes"] == {"type": ["dso"]}
        assert {m["id"] for m in fake.org_members[org["id"]]} == {
            "user-provider",
            "user-consumer",
        }
        assert {g["name"] for g in fake.org_groups[org["id"]]} == {
            "dataset.admin",
            "consumer",
        }
        assert len(fake.group_members) == 2
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_is_idempotent(self):
        """Re-running against the same realm creates nothing new."""
        fake = FakeKeycloak(USERS)
        kc = await make_client(fake)
        await sync_organizations(CONFIG, kc)
        second = await sync_organizations(CONFIG, kc)

        assert second.organizations_created == []
        assert second.organizations_existing == ["example-org"]
        assert second.members_added == []
        # Group assignment is a PUT — always reasserted, never duplicated.
        assert len(fake.orgs) == 1
        assert len(fake.org_members[fake.orgs[0]["id"]]) == 2
        assert len(fake.org_groups[fake.orgs[0]["id"]]) == 2
        assert len(fake.group_members) == 2
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_missing_user_is_reported_not_fatal(self):
        fake = FakeKeycloak({"provider@example.test": "user-provider"})
        kc = await make_client(fake)
        report = await sync_organizations(CONFIG, kc)

        assert report.missing_users == ["consumer@example.test"]
        assert report.has_warnings
        # The org and the resolvable member are still provisioned.
        assert report.organizations_created == ["example-org"]
        assert report.members_added == ["example-org/provider@example.test"]
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_existing_org_is_reused_not_duplicated(self):
        fake = FakeKeycloak(USERS)
        fake.orgs.append(
            {"id": "org-preexisting", "alias": "example-org", "name": "Old Name"}
        )
        fake.org_groups["org-preexisting"] = []
        fake.org_members["org-preexisting"] = []

        kc = await make_client(fake)
        report = await sync_organizations(CONFIG, kc)

        assert report.organizations_created == []
        assert report.organizations_existing == ["example-org"]
        assert len(fake.orgs) == 1
        assert {m["id"] for m in fake.org_members["org-preexisting"]} == {
            "user-provider",
            "user-consumer",
        }
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_empty_config_is_a_noop(self):
        fake = FakeKeycloak(USERS)
        kc = await make_client(fake)
        report = await sync_organizations(OrganizationsConfig(), kc)

        assert report.organizations_created == []
        assert fake.orgs == []
        await kc.aclose()


class TestKeycloakAdminClient:
    @pytest.mark.asyncio
    async def test_authenticate_sends_admin_cli_password_grant(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"access_token": "tok-123"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        kc = await KeycloakAdminClient.authenticate(
            BASE_URL, REALM, admin_user="root", admin_password="s3cret", client=client
        )
        assert kc.token == "tok-123"
        assert captured["path"] == "/realms/master/protocol/openid-connect/token"
        assert "client_id=admin-cli" in captured["body"]
        assert "username=root" in captured["body"]
        assert "grant_type=password" in captured["body"]
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_authenticate_raises_on_bad_credentials(self):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(401))
        )
        with pytest.raises(httpx.HTTPStatusError):
            await KeycloakAdminClient.authenticate(
                BASE_URL, REALM, admin_user="x", admin_password="y", client=client
            )

    @pytest.mark.asyncio
    async def test_find_user_by_email_returns_none_when_absent(self):
        fake = FakeKeycloak({})
        kc = await make_client(fake)
        assert await kc.find_user_by_email("nobody@example.test") is None
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_add_org_member_posts_raw_uuid_body(self):
        """KC 26 expects the bare UUID, not a JSON object — regression guard."""
        fake = FakeKeycloak(USERS)
        kc = await make_client(fake)
        org, _ = await kc.ensure_organization(CONFIG.organizations[0])
        assert await kc.add_org_member(org["id"], "user-provider") is True
        assert fake.org_members[org["id"]] == [{"id": "user-provider"}]
        # Second add is a no-op, not a duplicate.
        assert await kc.add_org_member(org["id"], "user-provider") is False
        assert len(fake.org_members[org["id"]]) == 1
        await kc.aclose()

    @pytest.mark.asyncio
    async def test_org_groups_tolerates_404(self):
        """Older KC versions 404 on the org-groups endpoint; treat as empty."""
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"access_token": "t"})
                if r.url.path.endswith("/token")
                else httpx.Response(404)
            )
        )
        kc = await KeycloakAdminClient.authenticate(
            BASE_URL, REALM, admin_user="a", admin_password="b", client=client
        )
        assert await kc.get_org_groups("org-1") == []
        await kc.aclose()
