"""Keycloak Admin REST client — native organizations provisioning.

Used by ``ir-cli keycloak org-sync`` to provision KC native organizations
(KC 24+) from ``organizations.yaml``.  All operations are idempotent.

KC organizations provide portal-level gating parallel to the identity-registry
``OrganizationMembership`` table. For the realm side — `organizations.yaml`, the
`organization.<alias>.groups` claim and the org-sync step — see
``docs/services/keycloak.md``; for the membership registry itself, see
``docs/services/identity-registry.md``.
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

    # ── Service clients ──────────────────────────────────────────────────────

    async def ensure_service_client(
        self,
        client_id: str,
        *,
        name: str,
        scopes: list[str],
        audiences: list[str] | None = None,
    ) -> str:
        """Create (or find) a confidential client and return its secret.

        A third party running its own ds instance needs credentials for the
        service-to-service calls its connector makes — the identity registry,
        provenance, and the counterparty connector. Those are Keycloak clients in
        *this* realm, so the registry provisions them at promotion time rather
        than leaving an operator to hand-configure a realm per participant.

        Idempotent: an existing client is reused and its secret read back, so
        re-running promotion does not invalidate credentials already handed out.
        Rotation is a separate, explicit act.

        `audiences` is applied on every call, not only at creation. Scopes alone
        are not enough: every ds service verifies `aud`, so a client that holds
        the right grants and no audience mapper authenticates successfully and
        is then refused by each service it calls. Re-applying also repairs a
        client created before the mappers existed, which is the whole
        population provisioned until now.
        """
        existing = await self._request(
            "GET", "/clients", params={"clientId": client_id}
        )
        if not existing:
            await self._request(
                "POST",
                "/clients",
                {
                    "clientId": client_id,
                    "name": name,
                    "enabled": True,
                    # Service-to-service only: no browser flows, no user sessions.
                    "publicClient": False,
                    "serviceAccountsEnabled": True,
                    "standardFlowEnabled": False,
                    "directAccessGrantsEnabled": False,
                    "defaultClientScopes": scopes,
                },
            )
            existing = await self._request(
                "GET", "/clients", params={"clientId": client_id}
            )

        if not existing:
            raise RuntimeError(f"Keycloak client {client_id} could not be created")

        uuid = existing[0]["id"]
        await self._ensure_audience_mappers(uuid, audiences or [])
        secret = await self._request("GET", f"/clients/{uuid}/client-secret")
        if not secret or not secret.get("value"):
            secret = await self._request("POST", f"/clients/{uuid}/client-secret")
        return str((secret or {}).get("value", ""))

    async def _ensure_audience_mappers(self, uuid: str, audiences: list[str]) -> None:
        """Add one `oidc-audience-mapper` per audience, skipping those present.

        Existing mappers are read first rather than relying on the 409 that
        `_request` swallows: Keycloak answers 409 on a duplicate *name*, and a
        mapper renamed by hand would otherwise be added a second time under a
        new name, putting the audience in the token twice.
        """
        if not audiences:
            return

        current = (
            await self._request("GET", f"/clients/{uuid}/protocol-mappers/models")
            or []
        )
        have = {
            (m.get("config") or {}).get("included.client.audience")
            for m in current
            if m.get("protocolMapper") == "oidc-audience-mapper"
        }

        for audience in audiences:
            if audience in have:
                continue
            await self._request(
                "POST",
                f"/clients/{uuid}/protocol-mappers/models",
                {
                    "name": f"aud-{audience}",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-audience-mapper",
                    "config": {
                        "included.client.audience": audience,
                        "access.token.claim": "true",
                        "id.token.claim": "false",
                    },
                },
            )

    async def rotate_service_client_secret(self, client_id: str) -> str:
        """Issue a new secret, invalidating the previous one."""
        existing = await self._request(
            "GET", "/clients", params={"clientId": client_id}
        )
        if not existing:
            raise RuntimeError(f"Keycloak client {client_id} does not exist")
        uuid = existing[0]["id"]
        secret = await self._request("POST", f"/clients/{uuid}/client-secret")
        return str((secret or {}).get("value", ""))

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
