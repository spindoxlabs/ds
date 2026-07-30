"""The authenticated caller — service or user — normalized to one shape."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .bundles import expand_bundles
from .jwt import (
    extract_groups,
    extract_organizations,
    extract_realm_groups,
    extract_scopes,
    is_service_account,
)
from .models import Organization
from .permissions import has_exact_permission, has_permission


@dataclass(frozen=True)
class Principal:
    """A verified caller with its effective authority.

    The unified authorization rule lives in :meth:`grants`:

    * **service** principals authorize on their ``scope`` claim;
    * **user** principals authorize on their group membership, **expanded**
      through the role bundles in :mod:`ds_auth.bundles`.

    Both draw from the same permission vocabulary, so a call site asks for a
    permission (e.g. ``connector.provider.write``) without caring which kind of
    token satisfied it. The expansion is what lets the group vocabulary stay
    small enough to provision in a realm ds does not administer, without the
    call sites learning anything about it.
    """

    subject: str
    is_service: bool
    scopes: tuple[str, ...]
    groups: tuple[str, ...]
    organizations: tuple[Organization, ...] = ()
    # Realm-level groups only — deployment-wide grants, as distinct from the
    # per-organisation ones carried on each :class:`Organization`. `groups` above
    # is the flattened union both call sites and history expect.
    realm_groups: tuple[str, ...] = ()
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
            groups=tuple(extract_groups(claims)),
            organizations=tuple(extract_organizations(claims)),
            realm_groups=tuple(extract_realm_groups(claims)),
            group_aliases=dict(group_aliases or {}),
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
        """The grant set that governs this principal (scopes vs expanded groups).

        A service's scopes are already capabilities. A user's groups are role
        bundles, so they are expanded first — see
        :func:`ds_auth.bundles.expand_bundles` for the three rules, including why
        an unrecognised group still passes through as itself.
        """
        if self.is_service:
            return self.scopes
        return expand_bundles(self.groups, self.group_aliases)

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

        The rule:

        * not a member of ``alias`` → **False**. Membership is necessary.
        * authority within ``alias`` = that organisation's groups **plus** the
          realm-level groups, expanded through the role bundles. Realm groups are
          deployment-wide by construction: a realm that grants
          ``ds-participant-admin`` at realm level is asserting authority across the
          deployment, and that is a legitimate configuration for a single-participant
          one.

        A service principal has no organisations and therefore no per-organisation
        authority — services authorise on scopes and are never owner-scoped. Callers
        that must let services through should check :attr:`is_service` first, so the
        exemption is visible where it is granted rather than hidden in here.
        """
        organization = self.get_organization(alias)
        if organization is None:
            return False
        authority = expand_bundles(
            [*organization.groups, *self.realm_groups], self.group_aliases
        )
        return has_permission(authority, required)

    def grants_exactly(self, required: Iterable[str]) -> bool:
        """True only if a required permission is held by name.

        For machine-identity permissions the admin superset must not apply —
        see :func:`ds_auth.permissions.has_exact_permission`.
        """
        return has_exact_permission(self.authority, required)
