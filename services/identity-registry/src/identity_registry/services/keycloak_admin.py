"""Keycloak Admin REST client — native organizations provisioning.

Used by ``ir-cli keycloak org-sync`` to provision KC native organizations
(KC 24+) from ``organizations.yaml``.  All operations are idempotent.

KC organizations provide portal-level gating parallel to the identity-registry
``OrganizationMembership`` table; see ``docs/owner-identity-and-ownership.md``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class OrgMemberSpec(BaseModel, extra="ignore"):
    email: str
    groups: list[str] = Field(default_factory=list)


class OrganizationSpec(BaseModel, extra="ignore"):
    alias: str
    name: str = ""
    domains: list[str] = Field(default_factory=list)
    attributes: dict[str, list[str]] | None = None
    members: list[OrgMemberSpec] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or self.alias


class OrganizationsConfig(BaseModel, extra="ignore"):
    realm: str | None = None
    organizations: list[OrganizationSpec] = Field(default_factory=list)


class SyncReport(BaseModel):
    """Outcome of an org sync run — machine-readable for CI gating."""

    organizations_created: list[str] = Field(default_factory=list)
    organizations_existing: list[str] = Field(default_factory=list)
    members_added: list[str] = Field(default_factory=list)
    groups_assigned: list[str] = Field(default_factory=list)
    missing_users: list[str] = Field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(self.missing_users)


def load_organizations_config(path: Path) -> OrganizationsConfig:
    """Load and validate an organizations.yaml file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return OrganizationsConfig.model_validate(raw)


class KeycloakAdminClient:
    """Thin async wrapper around the Keycloak Admin REST API."""

    def __init__(
        self, base_url: str, realm: str, token: str, client: httpx.AsyncClient
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.token = token
        self._client = client

    @classmethod
    async def authenticate(
        cls,
        base_url: str,
        realm: str,
        *,
        admin_user: str,
        admin_password: str,
        client: httpx.AsyncClient | None = None,
    ) -> KeycloakAdminClient:
        owns_client = client is None
        client = client or httpx.AsyncClient(timeout=30.0)
        try:
            resp = await client.post(
                f"{base_url.rstrip('/')}/realms/master/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": admin_user,
                    "password": admin_password,
                },
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]
        except Exception:
            if owns_client:
                await client.aclose()
            raise
        return cls(base_url, realm, token, client)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        *,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        tolerate: tuple[int, ...] = (),
    ) -> Any:
        resp = await self._client.request(
            method,
            f"{self.base_url}/admin/realms/{self.realm}{path}",
            json=json_body,
            params=params,
            content=content,
            headers={
                "Authorization": f"Bearer {self.token}",
                **({"Content-Type": "application/json"} if content is not None else {}),
            },
        )
        # 409 means "already there" — every write here is idempotent by design.
        if resp.status_code == 409 or resp.status_code in tolerate:
            return None
        resp.raise_for_status()
        if not resp.content:
            return None
        return resp.json()

    # ── Users ────────────────────────────────────────────────────────────────

    async def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        users = await self._request(
            "GET", "/users", params={"email": email, "exact": "true"}
        )
        return users[0] if isinstance(users, list) and users else None

    # ── Organizations ────────────────────────────────────────────────────────

    async def get_organization_by_alias(self, alias: str) -> dict[str, Any] | None:
        # KC 26 search matches on name, not alias — list all and filter.
        orgs = await self._request("GET", "/organizations")
        if isinstance(orgs, list):
            for org in orgs:
                if org.get("alias") == alias:
                    return org
        return None

    async def ensure_organization(
        self, spec: OrganizationSpec
    ) -> tuple[dict[str, Any], bool]:
        """Create the organization if absent. Returns (org, created)."""
        existing = await self.get_organization_by_alias(spec.alias)
        if existing:
            return existing, False

        body: dict[str, Any] = {
            "name": spec.display_name,
            "alias": spec.alias,
            "enabled": True,
        }
        if spec.domains:
            body["domains"] = [{"name": d, "verified": False} for d in spec.domains]
        if spec.attributes:
            body["attributes"] = spec.attributes

        await self._request("POST", "/organizations", body)
        created = await self.get_organization_by_alias(spec.alias)
        if not created:
            raise RuntimeError(f"Failed to create organization {spec.alias}")
        return created, True

    async def get_org_members(self, org_id: str) -> list[dict[str, Any]]:
        members = await self._request("GET", f"/organizations/{org_id}/members")
        return members if isinstance(members, list) else []

    async def add_org_member(self, org_id: str, user_id: str) -> bool:
        """Add a user to an organization. Returns True if newly added."""
        members = await self.get_org_members(org_id)
        if any(m.get("id") == user_id for m in members):
            return False
        # KC 26 expects the raw user UUID as the request body, not a JSON object.
        await self._request(
            "POST", f"/organizations/{org_id}/members", content=user_id.encode()
        )
        return True

    # ── Organization groups ─────────────────────────────────────────────────

    async def get_org_groups(self, org_id: str) -> list[dict[str, Any]]:
        groups = await self._request(
            "GET", f"/organizations/{org_id}/groups", tolerate=(404,)
        )
        return groups if isinstance(groups, list) else []

    async def ensure_org_group(self, org_id: str, group_name: str) -> dict[str, Any]:
        for group in await self.get_org_groups(org_id):
            if group.get("name") == group_name:
                return group
        await self._request(
            "POST", f"/organizations/{org_id}/groups", {"name": group_name}
        )
        for group in await self.get_org_groups(org_id):
            if group.get("name") == group_name:
                return group
        raise RuntimeError(f"Failed to create org group {group_name}")

    async def ensure_user_in_org_group(
        self, org_id: str, group_id: str, user_id: str
    ) -> None:
        await self._request(
            "PUT",
            f"/organizations/{org_id}/groups/{group_id}/members/{user_id}",
            tolerate=(404,),
        )


async def sync_organizations(
    config: OrganizationsConfig, kc: KeycloakAdminClient
) -> SyncReport:
    """Provision KC organizations, members, and org groups. Idempotent."""
    report = SyncReport()

    for spec in config.organizations:
        org, created = await kc.ensure_organization(spec)
        org_id = org["id"]
        if created:
            report.organizations_created.append(spec.alias)
            log.info("Created organization %s (id=%s)", spec.alias, org_id)
        else:
            report.organizations_existing.append(spec.alias)
            log.info("Organization %s already exists (id=%s)", spec.alias, org_id)

        for member in spec.members:
            user = await kc.find_user_by_email(member.email)
            if not user:
                report.missing_users.append(member.email)
                log.warning("User %s not found in KC, skipping", member.email)
                continue

            user_id = user["id"]
            if await kc.add_org_member(org_id, user_id):
                report.members_added.append(f"{spec.alias}/{member.email}")
                log.info("Added %s to organization %s", member.email, spec.alias)

            for group_name in member.groups:
                group = await kc.ensure_org_group(org_id, group_name)
                await kc.ensure_user_in_org_group(org_id, group["id"], user_id)
                report.groups_assigned.append(
                    f"{spec.alias}/{member.email}/{group_name}"
                )
                log.info(
                    "Assigned group %s to %s in org %s",
                    group_name,
                    member.email,
                    spec.alias,
                )

    return report
