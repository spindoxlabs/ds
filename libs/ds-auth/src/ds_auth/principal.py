"""The authenticated caller — service or user — normalized to one shape."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .bundles import PLATFORM_ADMIN_ROLE, organisation_authority, platform_authority
from .jwt import (
    extract_organizations,
    extract_realm_roles,
    extract_scopes,
    is_service_account,
)
from .management_api import ORGANISATION_CLIENT_PREFIX, scope_satisfies
from .models import Organization
from .permissions import has_exact_permission, has_permission


@dataclass(frozen=True)
class Principal:
    """A verified caller with its effective authority.

    The unified authorization rule lives in :meth:`grants`:

    * **service** principals authorize on their ``scope`` claim;
    * **user** principals authorize on two levels, kept apart
      (:mod:`ds_auth.bundles`): **platform** grants from allowlisted realm roles
      (``realm_access.roles``), and **organisation** grants from each
      organisation's own groups, valid only for that organisation.

    Both draw from the same permission vocabulary, so a call site asks for a
    permission (e.g. ``connector.provider.write``) without caring which kind of
    token satisfied it. A realm-level ``groups`` claim is never read for
    authority: a realm group grants nothing.
    """

    subject: str
    is_service: bool
    scopes: tuple[str, ...]
    # `realm_access.roles`, verbatim. Only the roles in
    # `bundles.REALM_ROLE_BUNDLES` grant anything (see `platform_authority`).
    realm_roles: tuple[str, ...] = ()
    # Each carries the groups held *within* that organisation.
    organizations: tuple[Organization, ...] = ()
    # Layer B, carried so every expansion this principal performs uses the same
    # translation — `authority` and `grants_in` must not disagree about what a
    # foreign group name means.
    group_aliases: Mapping[str, str] = field(default_factory=dict, repr=False)
    claims: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_claims(
        cls, claims: dict, group_aliases: Mapping[str, str] | None = None
    ) -> Principal:
        service = is_service_account(claims)
        return cls(
            subject=str(claims.get("sub") or claims.get("client_id") or ""),
            is_service=service,
            scopes=tuple(extract_scopes(claims)),
            realm_roles=tuple(extract_realm_roles(claims)),
            organizations=tuple(extract_organizations(claims)),
            group_aliases=dict(group_aliases or {}),
            claims=claims,
        )

    @property
    def client_id(self) -> str | None:
        """The client a service token was issued to (Keycloak's `azp`)."""
        if not isinstance(self.claims, dict):
            return None
        value = self.claims.get("azp") or self.claims.get("client_id")
        return str(value) if value else None

    @property
    def organisation_context(self) -> str | None:
        """The participant context an **organisation actor** acts as, or ``None``.

        An organisation's client (`svc-ds-connector-<alias>`) carries the
        organisation's participant context as `sub` (a hardcoded-claim mapper) —
        the value EDC's v5 management API binds a caller to. A token from such a
        client is the organisation acting as itself: its connector, or a batch
        job the organisation runs. Not a person, and never a person's proxy.

        Classified by the client, not by the `sub`: a caller deciding *what* a
        token may do must not let the token's own claims choose its class. Whose
        participant it may act for is the caller's check — compare this value
        with its own context.
        """
        client = self.client_id or ""
        if self.is_service and client.startswith(ORGANISATION_CLIENT_PREFIX):
            return self.subject or None
        return None

    @property
    def is_organisation(self) -> bool:
        return self.organisation_context is not None

    @property
    def actor(self) -> str:
        """A stable key for who acted: ``org:<context>`` for an organisation."""
        context = self.organisation_context
        return f"org:{context}" if context else self.subject

    def grants_management_scope(self, required: str) -> bool:
        """EDC's scope grammar (`management-api[:resource]:action`), on this token.

        Only a service token carries such a scope; a person's groups never
        expand to one (`MANAGEMENT_API_SCOPES` is in no bundle).
        """
        return self.is_service and scope_satisfies(self.scopes, required)

    @property
    def organization_aliases(self) -> list[str]:
        return [o.alias for o in self.organizations]

    def get_organization(self, alias: str) -> Organization | None:
        for o in self.organizations:
            if o.alias == alias:
                return o
        return None

    def is_member_of(self, alias: str) -> bool:
        return any(o.alias == alias for o in self.organizations)

    @property
    def is_platform_admin(self) -> bool:
        """A person holding the ``platform-admin`` realm role. Never a service."""
        return not self.is_service and PLATFORM_ADMIN_ROLE in self.realm_roles

    @property
    def platform_authority(self) -> tuple[str, ...]:
        """What this person may do **everywhere**: allowlisted realm roles, expanded.

        Empty for a service, which authorises on scopes.
        """
        if self.is_service:
            return ()
        return platform_authority(self.realm_roles)

    def authority_in(self, alias: str) -> tuple[str, ...]:
        """What this person's groups **in** ``alias`` grant — that organisation only.

        Empty when not a member, and for a service. Does not include
        :attr:`platform_authority`; :meth:`grants_in` adds it.
        """
        if self.is_service:
            return ()
        organization = self.get_organization(alias)
        if organization is None:
            return ()
        return organisation_authority(organization.groups, self.group_aliases)

    @property
    def authority(self) -> tuple[str, ...]:
        """The grant set a route-level guard checks: *may this caller do X at all*.

        A service's scopes are already capabilities. A person's is the platform
        authority plus what each of their organisations grants within itself.

        The organisation part answers "somewhere", never "here": it can only hold
        :data:`ds_auth.bundles.ORGANISATION_PERMISSIONS` — never a
        ``{service}.admin`` superset or a platform-only permission — so it cannot
        add up to a platform grant, however many organisations a person is in. A
        perimeter on a resource that belongs to an owner must still ask
        :meth:`grants_in`.
        """
        if self.is_service:
            return self.scopes
        capabilities = list(self.platform_authority)
        for organization in self.organizations:
            capabilities.extend(self.authority_in(organization.alias))
        return tuple(dict.fromkeys(capabilities))

    def grants(self, *required: str) -> bool:
        """True if this principal holds any of the ``required`` permissions."""
        return has_permission(self.authority, required)

    def grants_any(self, required: Iterable[str]) -> bool:
        return has_permission(self.authority, required)

    def grants_in(self, alias: str, *required: str) -> bool:
        """True if this principal holds a required permission **for one organisation**.

        :meth:`grants` asks *what* a caller may do; this asks *whose* data they may
        do it to. The difference is not cosmetic: a person can legitimately be a
        read-only auditor for one participant and an administrator for another, and
        flattened authority reports them as an administrator everywhere.

        The rule — the two levels, and nothing else:

        * the **platform** authority (allowlisted realm roles) holds everywhere,
          member or not;
        * otherwise, only ``alias``'s **own** groups count, and only for a member.
          No other organisation's groups, and no realm-level group, ever do.

        A service principal has no per-organisation authority — services authorise
        on scopes and are never owner-scoped. Callers that must let services
        through should check :attr:`is_service` first, so the exemption is visible
        where it is granted rather than hidden in here.
        """
        if self.is_service:
            return False
        return has_permission(
            (*self.platform_authority, *self.authority_in(alias)), required
        )

    def grants_exactly(self, required: Iterable[str]) -> bool:
        """True only if a required permission is held by name.

        For machine-identity permissions the admin superset must not apply —
        see :func:`ds_auth.permissions.has_exact_permission`.
        """
        return has_exact_permission(self.authority, required)
