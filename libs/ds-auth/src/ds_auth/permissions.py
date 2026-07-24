"""Permission matching — the unified rule shared by service and user tokens.

Permissions are ``{service}.{resource}.{action}`` strings (celine convention),
with ``{service}.admin`` acting as a superset that satisfies any ``{service}.*``.
The *same* string is a granted scope on a service token and a granted group on a
user token — that symmetry is what lets one guard authorize both principals.
"""
from __future__ import annotations

from collections.abc import Iterable

_ADMIN_SUFFIX = ".admin"


def grant_satisfies(grant: str, required: str) -> bool:
    """True if a single held ``grant`` satisfies a single ``required`` permission."""
    if grant == required:
        return True
    if grant.endswith(_ADMIN_SUFFIX):
        service = grant[: -len(_ADMIN_SUFFIX)]
        # {service}.admin grants {service}.admin and any {service}.<...>
        return required == grant or required.startswith(f"{service}.")
    return False


def has_permission(grants: Iterable[str], required: Iterable[str]) -> bool:
    """True if any held grant satisfies any of the required permissions."""
    grant_list = list(grants)
    return any(grant_satisfies(g, r) for r in required for g in grant_list)


def has_exact_permission(grants: Iterable[str], required: Iterable[str]) -> bool:
    """True only if a required permission is held **by name**.

    The admin superset is right for permissions that describe *authority over a
    resource*: someone who administers the connector may obviously read its
    assets. It is wrong for permissions that describe *being a particular
    machine* — accepting EDC webhook callbacks, or reading the EDR signing keys
    over the internal API. Those are not privileges an administrator should
    inherit by virtue of being an administrator; holding them means "I am that
    component", and an admin is not.

    Use this for capabilities where the answer to "should the platform operator
    be able to do this with their own token?" is no.
    """
    grant_set = set(grants)
    return any(r in grant_set for r in required)
