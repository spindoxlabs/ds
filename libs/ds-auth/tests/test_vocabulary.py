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


#: Generated artefacts that sit beside the overlays and match the same glob.
#: Excluded deliberately: `clients.effective.yaml` is core + every overlay, so
#: counting it as a source would make every assertion below tautological — a
#: permission declared nowhere would still appear "declared".
_GENERATED = {"clients.effective.yaml", "clients.host.generated.yaml"}


def _overlay_paths() -> list[Path]:
    return sorted(
        p for p in KEYCLOAK.glob("clients.*.yaml") if p.name not in _GENERATED
    )


def _all_scopes() -> set[str]:
    """Core plus every domain overlay (`clients.<domain>.yaml`).

    Domain scopes are lifted out of the core file (R1), so a permission may
    legitimately live in an overlay. The union is what a realm actually gets — it
    is what `ir-cli keycloak merge` hands the sync.
    """
    scopes = _core_scopes()
    for path in _overlay_paths():
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
    invented = all_bundled_permissions() - _core_scopes()
    assert not invented, (
        f"bundles grant permissions absent from clients.yaml: {sorted(invented)}"
    )


def test_no_bundle_reaches_into_a_domain_backends_vocabulary():
    """Layer A is ds's own semantics, and stops at ds's own permissions.

    A domain overlay (`clients.<domain>.yaml`) declares what the backend deployed
    alongside ds needs. Granting one of its scopes through a ds bundle would make
    a ds seat mean something different depending on which backend happens to be
    deployed — and would break outright in a deployment carrying a different
    overlay, or none.
    """
    overlay_scopes = _all_scopes() - _core_scopes()
    reached = all_bundled_permissions() & overlay_scopes
    assert not reached, (
        f"bundles grant domain-overlay permissions: {sorted(reached)} — a ds bundle "
        "may only expand to scopes declared in the core clients.yaml"
    )


def test_service_only_declarations_are_not_stale():
    """Checked against the **core** file only.

    A domain overlay's scopes are not ds's to classify, and a deployment may carry
    a different overlay or none at all — so naming one here would make this suite
    fail on a stack that is perfectly correct.
    """
    stale = SERVICE_ONLY_PERMISSIONS - _core_scopes()
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


# ── The host-realm mirror ────────────────────────────────────────────────────
#
# Where ds is a guest, the host realm's `clients.yaml` must carry the same clients
# and scopes. That copy was hand-maintained, and every row of drift found so far —
# `svc-edc` missing `connector.internal`, `svc-ds-provenance` declared in neither
# file, `svc-ds-portal` holding `connector.admin` — is a symptom of two files
# edited by hand and compared by eye. It is generated now; this is the gate.


def _mirror_module():
    """The generator, imported normally — it lives in the identity-registry package
    because `ir-cli` already owns the `keycloak` command surface."""
    import sys

    src = REPO / "services" / "identity-registry" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from identity_registry.services import keycloak_mirror

    return keycloak_mirror


def test_the_generated_mirror_is_not_stale():
    """If this fails, `clients.yaml` changed and the mirror did not — run
    `task keycloak:mirror` and commit the result."""
    mirror = _mirror_module()
    source = yaml.safe_load(mirror.SOURCE.read_text(encoding="utf-8"))
    assert mirror.TARGET.exists(), "mirror missing — run `task keycloak:mirror`"
    assert mirror.TARGET.read_text(encoding="utf-8") == mirror.render(source), (
        "mirror is stale — run `task keycloak:mirror`"
    )


def test_the_mirror_carries_no_admin_grant():
    """Admin is an *operator* grant and a superset over every `{service}.*`. A
    long-lived process should not hold one, and a copy must not quietly widen what
    the original granted."""
    mirror = _mirror_module()
    source = yaml.safe_load(mirror.SOURCE.read_text(encoding="utf-8"))
    built = mirror.build_mirror(source)
    for client in built["clients"]:
        leaked = [s for s in client["default_scopes"] if s.endswith(".admin")]
        assert not leaked, f"{client['client_id']} crosses with {leaked}"
    assert not [s for s in built["scopes"] if s["name"].endswith(".admin")]


def test_the_test_identity_never_crosses():
    """`svc-ds-e2e` is dev/CI only and deliberately over-granted. A test identity
    in a production realm is a permanent credential nobody audits."""
    mirror = _mirror_module()
    source = yaml.safe_load(mirror.SOURCE.read_text(encoding="utf-8"))
    ids = {c["client_id"] for c in mirror.build_mirror(source)["clients"]}
    assert "svc-ds-e2e" not in ids


def test_every_other_client_does_cross():
    """Provisioned-but-unused is harmless; missing is a 403 at the worst moment.
    So a client whose grants are *entirely* admin still crosses, with none."""
    mirror = _mirror_module()
    source = yaml.safe_load(mirror.SOURCE.read_text(encoding="utf-8"))
    declared = {c["client_id"] for c in source["clients"]} - {"svc-ds-e2e"}
    crossed = {c["client_id"] for c in mirror.build_mirror(source)["clients"]}
    assert declared == crossed
