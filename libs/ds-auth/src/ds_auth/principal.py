"""The authenticated caller — service or user — normalized to one shape."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .jwt import extract_groups, extract_organizations, extract_scopes, is_service_account
from .models import Organization
from .permissions import has_exact_permission, has_permission


@dataclass(frozen=True)
class Principal:
    """A verified caller with its effective authority.

    The unified authorization rule lives in :meth:`grants`:

    * **service** principals authorize on their ``scope`` claim;
    * **user** principals authorize on their group membership.

    Both draw from the same permission vocabulary, so a call site asks for a
    permission (e.g. ``connector.provider.write``) without caring which kind of
    token satisfied it.
    """

    subject: str
    is_service: bool
    scopes: tuple[str, ...]
    groups: tuple[str, ...]
    organizations: tuple[Organization, ...] = ()
    claims: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_claims(cls, claims: dict) -> Principal:
        service = is_service_account(claims)
        return cls(
            subject=str(claims.get("sub") or claims.get("client_id") or ""),
            is_service=service,
            scopes=tuple(extract_scopes(claims)),
            groups=tuple(extract_groups(claims)),
            organizations=tuple(extract_organizations(claims)),
            claims=claims,
        )

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
    def authority(self) -> tuple[str, ...]:
        """The grant set that governs this principal (scopes vs groups)."""
        return self.scopes if self.is_service else self.groups

    def grants(self, *required: str) -> bool:
        """True if this principal holds any of the ``required`` permissions."""
        return has_permission(self.authority, required)

    def grants_any(self, required: Iterable[str]) -> bool:
        return has_permission(self.authority, required)

    def grants_exactly(self, required: Iterable[str]) -> bool:
        """True only if a required permission is held by name.

        For machine-identity permissions the admin superset must not apply —
        see :func:`ds_auth.permissions.has_exact_permission`.
        """
        return has_exact_permission(self.authority, required)
