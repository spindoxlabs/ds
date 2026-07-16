"""The authenticated caller — service or user — normalized to one shape."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .jwt import extract_groups, extract_scopes, is_service_account
from .permissions import has_permission


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
    claims: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_claims(cls, claims: dict) -> Principal:
        service = is_service_account(claims)
        return cls(
            subject=str(claims.get("sub") or claims.get("client_id") or ""),
            is_service=service,
            scopes=tuple(extract_scopes(claims)),
            groups=tuple(extract_groups(claims)),
            claims=claims,
        )

    @property
    def authority(self) -> tuple[str, ...]:
        """The grant set that governs this principal (scopes vs groups)."""
        return self.scopes if self.is_service else self.groups

    def grants(self, *required: str) -> bool:
        """True if this principal holds any of the ``required`` permissions."""
        return has_permission(self.authority, required)

    def grants_any(self, required: Iterable[str]) -> bool:
        return has_permission(self.authority, required)
