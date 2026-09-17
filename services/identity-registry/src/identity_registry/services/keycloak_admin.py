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
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import yaml
from ds_auth import is_management_api_scope
from ds_auth.production import is_production
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
    #: The organisation's EDC participant context id. When set, the sync also
    #: ensures the organisation's client (`svc-ds-connector-<alias>`), whose
    #: tokens carry this value as `sub` — the caller EDC's v5 management API
    #: binds to a participant context. Absent: the organisation has no client.
    participant_context_id: str | None = None

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
    clients_ensured: list[str] = Field(default_factory=list)
    #: Existing clients whose secret differs from the one configured. Never
    #: rewritten — a live client's credential changes only by rotation.
    clients_with_other_secret: list[str] = Field(default_factory=list)
    #: Organisation clients not provisioned, with the reason.
    client_errors: list[str] = Field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(
            self.missing_users or self.clients_with_other_secret or self.client_errors
        )


def load_organizations_config(path: Path) -> OrganizationsConfig:
    """Load and validate an organizations.yaml file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return OrganizationsConfig.model_validate(raw)


#: The protocol mapper that sets an organisation client's `sub`.
SUBJECT_MAPPER_NAME = "participant-context-sub"


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
        subject: str | None = None,
        secret: str | None = None,
    ) -> str:
        """Create (or find) a confidential client and return its secret.

        A third party running its own ds instance needs credentials for the
        service-to-service calls its connector makes — the identity registry,
        provenance, and the counterparty connector. Those are Keycloak clients in
        *this* realm, so the registry provisions them at promotion time rather
        than leaving an operator to hand-configure a realm per participant.

        Idempotent: an existing client is reused and its secret read back, so
        re-running promotion does not invalidate credentials already handed out.
        Rotation is a separate, explicit act. `secret` is applied **only when the
        client is created** — the same rule the realm sync follows — and is
        otherwise left to the caller to compare with what is returned.

        `audiences`, `scopes` and `subject` are applied on every call, not only
        at creation, which is also the repair path for a client created before
        each existed:

        - **audiences** — every ds service verifies `aud`, so a client with the
          right grants and no audience mapper authenticates and is then refused;
        - **scopes** — missing default scopes are added, and a `management-api`
          scope not in `scopes` is removed. Other scopes Keycloak assigned at
          creation (the realm defaults) are left alone;
        - **subject** — a hardcoded `sub`. EDC's v5 management API reads the
          caller's participant context from `sub`, which Keycloak otherwise sets
          to the service account's UUID.
        """
        existing = await self._request(
            "GET", "/clients", params={"clientId": client_id}
        )
        if not existing:
            body: dict[str, Any] = {
                "clientId": client_id,
                "name": name,
                "enabled": True,
                # Service-to-service only: no browser flows, no user sessions.
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "defaultClientScopes": scopes,
            }
            if secret:
                body["secret"] = secret
            await self._request("POST", "/clients", body)
            existing = await self._request(
                "GET", "/clients", params={"clientId": client_id}
            )

        if not existing:
            raise RuntimeError(f"Keycloak client {client_id} could not be created")

        uuid = existing[0]["id"]
        await self._ensure_default_scopes(uuid, scopes)
        await self._ensure_audience_mappers(uuid, audiences or [])
        if subject:
            await self._ensure_subject_mapper(uuid, subject)
        current = await self._request("GET", f"/clients/{uuid}/client-secret")
        if not current or not current.get("value"):
            current = await self._request("POST", f"/clients/{uuid}/client-secret")
        return str((current or {}).get("value", ""))

    async def _ensure_default_scopes(self, uuid: str, scopes: list[str]) -> None:
        """Add the missing default scopes; drop any unlisted `management-api` one.

        Keycloak ignores an unknown scope name on client creation without a word,
        and assigns nothing on a client that already exists. A scope the realm
        does not declare is therefore an error here, not a silent gap: the client
        would look provisioned and be refused by whatever checks the scope.
        """
        current = (
            await self._request("GET", f"/clients/{uuid}/default-client-scopes") or []
        )
        have = {s.get("name"): s.get("id") for s in current}
        wanted = set(scopes)

        missing = [s for s in scopes if s not in have]
        if missing:
            realm_scopes = await self._request("GET", "/client-scopes") or []
            ids = {s.get("name"): s.get("id") for s in realm_scopes}
            undeclared = [s for s in missing if s not in ids]
            if undeclared:
                raise RuntimeError(
                    f"the realm declares no client scope {undeclared} — sync "
                    "services/keycloak/clients.yaml before provisioning clients"
                )
            for scope in missing:
                await self._request(
                    "PUT", f"/clients/{uuid}/default-client-scopes/{ids[scope]}"
                )

        for name_, scope_id in have.items():
            if name_ and is_management_api_scope(name_) and name_ not in wanted:
                await self._request(
                    "DELETE",
                    f"/clients/{uuid}/default-client-scopes/{scope_id}",
                    tolerate=(404,),
                )

    async def _ensure_subject_mapper(self, uuid: str, subject: str) -> None:
        """One hardcoded `sub` claim on the access token, set to `subject`.

        Verified on Keycloak 26.7.3, with and without the stock `basic` scope:
        the token carries a single `sub` with this value. An existing mapper
        with another value is corrected — the organisation's participant
        context is what the declaration says it is.
        """
        body = {
            "name": SUBJECT_MAPPER_NAME,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-hardcoded-claim-mapper",
            "config": {
                "claim.name": "sub",
                "claim.value": subject,
                "jsonType.label": "String",
                "access.token.claim": "true",
                "id.token.claim": "false",
                "userinfo.token.claim": "false",
                "introspection.token.claim": "true",
            },
        }
        current = (
            await self._request("GET", f"/clients/{uuid}/protocol-mappers/models") or []
        )
        for mapper in current:
            if mapper.get("name") != SUBJECT_MAPPER_NAME:
                continue
            if (mapper.get("config") or {}).get("claim.value") == subject:
                return
            log.warning(
                "client %s: sub mapper named %r, correcting to %r",
                uuid,
                (mapper.get("config") or {}).get("claim.value"),
                subject,
            )
            await self._request(
                "PUT",
                f"/clients/{uuid}/protocol-mappers/models/{mapper['id']}",
                {**body, "id": mapper["id"]},
            )
            return
        await self._request("POST", f"/clients/{uuid}/protocol-mappers/models", body)

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
            await self._request("GET", f"/clients/{uuid}/protocol-mappers/models") or []
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


class OrganisationClientSecretError(ValueError):
    """No usable secret for an organisation client in this environment."""


def secret_env_name(client_id: str) -> str:
    """`svc-ds-connector-example-rec` → `SVC_DS_CONNECTOR_EXAMPLE_REC_SECRET`.

    The same convention as every `SVC_<CLIENT>_SECRET` in `clients.yaml`.
    """
    return client_id.upper().replace("-", "_") + "_SECRET"


def organisation_client_secret(
    client_id: str,
    *,
    environ: Mapping[str, str] | None = None,
    production: bool | None = None,
) -> str:
    """The secret an organisation client is created with.

    Dev keeps the zero-config default every ds client has — the client id. Under
    `DS_ENV=production` there is no default: the variable must be set, and set to
    something other than the client id, or the client is not provisioned.
    """
    environ = os.environ if environ is None else environ
    production = is_production() if production is None else production
    name = secret_env_name(client_id)
    value = (environ.get(name) or "").strip()
    if production:
        if not value:
            raise OrganisationClientSecretError(
                f"{client_id}: {name} is not set (DS_ENV=production has no default)"
            )
        if value == client_id:
            raise OrganisationClientSecretError(
                f"{client_id}: {name} equals the client id, the dev default"
            )
    return value or client_id


async def ensure_organisation_client(
    kc: KeycloakAdminClient,
    *,
    alias: str,
    name: str,
    participant_context_id: str,
    secret: str | None = None,
) -> tuple[str, str]:
    """Ensure `svc-ds-connector-<alias>`: organisation scopes, audiences, `sub`.

    Returns (client id, the secret Keycloak holds). The one definition of an
    organisation client, shared by `org-sync` and the provisioning bundle.
    """
    from ds_auth import organisation_client_id

    from .provisioning import CONNECTOR_AUDIENCES, ORGANISATION_CLIENT_SCOPES

    client_id = organisation_client_id(alias)
    held = await kc.ensure_service_client(
        client_id,
        name=f"ds connector — {name}",
        scopes=list(ORGANISATION_CLIENT_SCOPES),
        audiences=list(CONNECTOR_AUDIENCES),
        subject=participant_context_id,
        secret=secret,
    )
    return client_id, held


async def sync_organizations(
    config: OrganizationsConfig,
    kc: KeycloakAdminClient,
    *,
    environ: Mapping[str, str] | None = None,
    production: bool | None = None,
) -> SyncReport:
    """Provision KC organizations, members, org groups and org clients. Idempotent."""
    report = SyncReport()

    for spec in config.organizations:
        if spec.participant_context_id:
            await _sync_organisation_client(
                spec, kc, report, environ=environ, production=production
            )

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


async def _sync_organisation_client(
    spec: OrganizationSpec,
    kc: KeycloakAdminClient,
    report: SyncReport,
    *,
    environ: Mapping[str, str] | None,
    production: bool | None,
) -> None:
    from ds_auth import organisation_client_id

    client_id = organisation_client_id(spec.alias)
    try:
        secret = organisation_client_secret(
            client_id, environ=environ, production=production
        )
    except OrganisationClientSecretError as exc:
        report.client_errors.append(str(exc))
        log.error("%s — client not provisioned", exc)
        return

    _, held = await ensure_organisation_client(
        kc,
        alias=spec.alias,
        name=spec.display_name,
        participant_context_id=spec.participant_context_id or "",
        secret=secret,
    )
    report.clients_ensured.append(client_id)
    if held != secret:
        report.clients_with_other_secret.append(client_id)
        log.warning(
            "%s exists with a different secret; left unchanged (%s is applied "
            "only when the client is created)",
            client_id,
            secret_env_name(client_id),
        )
