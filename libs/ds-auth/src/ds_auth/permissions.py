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
