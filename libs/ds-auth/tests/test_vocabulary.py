"""The bundle table and the scope vocabulary must describe the same platform.

Two artifacts define authority: `services/keycloak/clients.yaml` declares what a
*service* may hold, and `ds_auth.bundles` declares what a *human* may hold. They
are deliberately no longer the same strings — but they must stay reconcilable, or
the failure mode is a permission nobody can be granted (silently unreachable UI)
or a bundle granting a name the realm never defines (a grant that matches
nothing, discovered at 403 time).

These are the CI assertions called for by A2 in
`.agents/plans/ds-identity-and-deployment.md`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ds_auth import (
    MACHINE_IDENTITY_PERMISSIONS,
    ROLE_BUNDLES,
    SERVICE_ONLY_PERMISSIONS,
    all_bundled_permissions,
)

REPO = Path(__file__).resolve().parents[3]
KEYCLOAK = REPO / "services" / "keycloak"


def _declared_scopes(path: Path) -> set[str]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {s["name"] for s in document.get("scopes") or [] if s.get("name")}


def _core_scopes() -> set[str]:
    return _declared_scopes(KEYCLOAK / "clients.yaml")


def _all_scopes() -> set[str]:
    """Core plus any domain overlay (`clients.<domain>.yaml`).

    Domain scopes are being lifted out of the core file, so a permission may
    legitimately live in an overlay. The union is what a realm actually gets.
    """
    scopes: set[str] = set()
    for path in sorted(KEYCLOAK.glob("clients*.yaml")):
        scopes |= _declared_scopes(path)
    return scopes


def test_the_vocabulary_file_is_where_we_think_it_is():
    """A wrong path would make every assertion below vacuously true."""
    assert (KEYCLOAK / "clients.yaml").is_file()
    assert _core_scopes(), "no scopes parsed from clients.yaml"


def test_every_scope_is_reachable_or_declared_service_only():
    """No orphan permissions.

    A scope that no bundle expands to and that is not declared service-only is a
    capability no human can ever be granted — almost always a bundle the author
    forgot to extend rather than a deliberate choice.
    """
    orphans = _core_scopes() - all_bundled_permissions() - SERVICE_ONLY_PERMISSIONS
    assert not orphans, (
        f"scopes reachable by nobody: {sorted(orphans)} — add them to a bundle in "
        "ds_auth.bundles.ROLE_BUNDLES, or declare them in SERVICE_ONLY_PERMISSIONS "
        "with a reason"
    )


def test_no_bundle_grants_an_undeclared_permission():
    """The inverse: a bundle may not invent a capability.

    A bundle granting a name the realm never declares as a scope produces a
    grant that satisfies nothing — visible only when a route 403s.
    """
    invented = all_bundled_permissions() - _all_scopes()
    assert not invented, (
        f"bundles grant permissions absent from clients.yaml: {sorted(invented)}"
    )


def test_service_only_declarations_are_not_stale():
    stale = SERVICE_ONLY_PERMISSIONS - _all_scopes()
    assert not stale, (
        f"SERVICE_ONLY_PERMISSIONS names scopes that no longer exist: {sorted(stale)}"
    )


def test_machine_identity_permissions_exist_as_scopes():
    """They are real grants a service holds — just never a human one."""
    missing = MACHINE_IDENTITY_PERMISSIONS - _core_scopes()
    assert not missing, f"machine-identity permissions not declared: {sorted(missing)}"


@pytest.mark.parametrize("bundle", sorted(ROLE_BUNDLES))
def test_bundle_names_do_not_collide_with_scope_names(bundle: str):
    """A bundle named like a scope would be ambiguous.

    `expand_bundles` passes unknown groups through verbatim, so a name that is
    *both* a bundle and a scope would expand instead of passing through — and
    which behaviour applied would depend on the order the two artifacts were
    edited in.
    """
    assert bundle not in _all_scopes(), (
        f"{bundle} is both a role bundle and a declared scope"
    )


@pytest.mark.parametrize("bundle", sorted(ROLE_BUNDLES))
def test_every_bundle_grants_something(bundle: str):
    assert ROLE_BUNDLES[bundle], f"{bundle} expands to nothing"
