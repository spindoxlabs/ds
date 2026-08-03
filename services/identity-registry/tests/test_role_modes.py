"""Role modes — what each role mounts, and the sweep that keeps it true (`DID-04`).

The interesting tests here are not the ones asserting that a participant has no
`/admin`. They are the ones asserting that **the sweep notices** when the two
halves of `roles.py` disagree — because that is what has to keep working as
routes are added by people who have never read this file.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from identity_registry import roles
from identity_registry.config import Settings, get_settings
from identity_registry.main import create_app
from identity_registry.roles import (
    PARTICIPANT,
    ROUTERS,
    TRUST_ANCHOR,
    RoleConfigurationError,
    audit,
    normalize_role,
    roles_for_path,
    specs_for_role,
)


def paths_for(role: str, monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """Every path an instance of *role* actually serves.

    A participant needs a DID: an instance that does not know which organisation
    it is refuses to start, because every route it mounts answers *for a DID it
    holds*. Setting one here is not test scaffolding around an inconvenience —
    it is the configuration a participant genuinely has.
    """
    monkeypatch.setenv("IDENTITY_REGISTRY_ROLE", role)
    monkeypatch.setenv(
        "IDENTITY_REGISTRY_PARTICIPANT_DID", "did:web:rec.dataspaces.localhost"
    )
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        return set(client.get("/openapi.json").json()["paths"])
    finally:
        get_settings.cache_clear()


# ── What each role serves ─────────────────────────────────────────


ANCHOR_ONLY_SAMPLES = [
    "/admin/participants",
    "/admin/credentials/data-subject",
    "/admin/owners",
    "/admin/onboarding/invites",
    "/onboarding/applications",
    "/agreements/current",
    "/memberships/check",
    "/owners/resolve",
    "/status/{list_id}",
    "/credentials/check",
]

HOLDER_SAMPLES = [
    "/sts/{did}/token",
    "/credentials/{did}/presentations/query",
    "/dids/{did}/did.json",
    "/.well-known/did.json",
]


@pytest.mark.parametrize("path", ANCHOR_ONLY_SAMPLES)
def test_participant_serves_no_anchor_route(path, monkeypatch):
    assert path not in paths_for(PARTICIPANT, monkeypatch)


@pytest.mark.parametrize("path", ANCHOR_ONLY_SAMPLES)
def test_anchor_serves_its_own_routes(path, monkeypatch):
    assert path in paths_for(TRUST_ANCHOR, monkeypatch)


@pytest.mark.parametrize("path", HOLDER_SAMPLES)
def test_participant_serves_the_holder_surface(path, monkeypatch):
    assert path in paths_for(PARTICIPANT, monkeypatch)


def test_health_is_served_by_both_and_names_the_role(monkeypatch):
    monkeypatch.setenv(
        "IDENTITY_REGISTRY_PARTICIPANT_DID", "did:web:rec.dataspaces.localhost"
    )
    for role in (TRUST_ANCHOR, PARTICIPANT):
        monkeypatch.setenv("IDENTITY_REGISTRY_ROLE", role)
        get_settings.cache_clear()
        body = TestClient(create_app()).get("/health").json()
        assert body["role"] == role
    get_settings.cache_clear()


def test_the_anchor_is_still_a_superset(monkeypatch):
    """Until `DID-05` the anchor is also everyone's STS and credential service.

    Narrowing it is a *data* change (`DID-12`), not a route change — removing
    the holder routes here would take the dev stack down before the participant
    instances that replace them exist. `IR-10`, one more time.
    """
    anchor = paths_for(TRUST_ANCHOR, monkeypatch)
    participant = paths_for(PARTICIPANT, monkeypatch)
    assert participant < anchor
    assert participant  # and it is not empty, which would pass vacuously


# ── The sweep itself ──────────────────────────────────────────────


def test_every_mounted_path_is_classified_for_both_roles():
    """The startup assertion, run directly. `create_app` raises if this fails."""
    for role in (TRUST_ANCHOR, PARTICIPANT):
        mounted = ["/health"]
        for spec in specs_for_role(role):
            mounted.extend(spec.paths())
        assert audit(role, mounted) == []


def test_an_unclassified_path_is_reported():
    problems = audit(TRUST_ANCHOR, ["/health", "/brand/new/route"])
    assert any("/brand/new/route" in p and "PATH_ROLES" in p for p in problems)


def test_a_path_mounted_on_the_wrong_role_is_reported():
    problems = audit(PARTICIPANT, ["/admin/participants"])
    assert any(
        "/admin/participants" in p and "restricts it to" in p for p in problems
    )


def test_a_classified_router_that_is_not_mounted_is_reported():
    """The other direction: a role that *should* serve a path and does not."""
    problems = audit(TRUST_ANCHOR, ["/health"])
    assert any("is not mounted" in p for p in problems)


def test_audit_reports_every_problem_not_the_first():
    problems = audit(PARTICIPANT, ["/admin/participants", "/brand/new/route"])
    assert len([p for p in problems if "/admin/participants" in p]) == 1
    assert len([p for p in problems if "/brand/new/route" in p]) == 1


def test_a_new_router_mounted_without_classification_refuses_startup(monkeypatch):
    """The failure this sweep exists for, end to end.

    Someone adds a router and mounts it. Nothing else in the service would
    notice; the route would simply be served by whichever role happened to mount
    it, including a participant instance serving something only the anchor
    should.
    """
    rogue = APIRouter(prefix="/rogue")

    @rogue.get("/thing")
    async def _thing():  # pragma: no cover - never called
        return {}

    spec = roles.RouterSpec("rogue", rogue, roles.BOTH)
    monkeypatch.setattr(roles, "ROUTERS", (*ROUTERS, spec))

    get_settings.cache_clear()
    with pytest.raises(RoleConfigurationError) as excinfo:
        create_app()
    assert "/rogue/thing" in str(excinfo.value)
    get_settings.cache_clear()


def test_a_stale_classification_entry_is_visible():
    """Every `PATH_ROLES` prefix classifies something that exists.

    A table of paths nobody serves is how the two halves drift apart without
    either one being wrong on its own — the entry stays, the route goes, and the
    next reader trusts a rule that governs nothing.
    """
    served = {
        roles._strip_converters(path)
        for spec in ROUTERS
        for path in spec.paths()
    } | {"/health"}

    unused = [
        prefix
        for prefix, _ in roles.PATH_ROLES
        if not any(
            p == prefix or p.startswith(prefix.rstrip("/") + "/") for p in served
        )
    ]
    assert unused == []


# ── Classification rules ──────────────────────────────────────────


def test_longest_prefix_wins():
    assert roles_for_path("/credentials/check") == roles.ANCHOR_ONLY
    assert roles_for_path("/credentials/did:web:x/presentations/query") == roles.HOLDER


def test_converters_do_not_change_the_classification():
    assert roles_for_path("/sts/{did:path}/token") == roles_for_path(
        "/sts/{did}/token"
    )
    assert roles_for_path("/{did_path:path}/did.json") is not None


def test_the_catch_all_does_not_swallow_a_specific_path():
    """`/{did_path}/did.json` matches anything ending in `/did.json`.

    If it were allowed to win, `/admin/...` would classify as a holder route the
    moment someone added `/admin/something/did.json`. Longest prefix is what
    stops that, and this is the assertion that says so.
    """
    assert roles_for_path("/admin/participants") == roles.ANCHOR_ONLY


# ── Role names ────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["trust-anchor", "TRUST-ANCHOR", " participant "])
def test_role_names_are_normalized(value):
    assert normalize_role(value) in roles.ROLES


@pytest.mark.parametrize("value", ["", "anchor", "participants", "issuer", None])
def test_an_unknown_role_is_refused(value):
    """Never a fallback to `trust-anchor`.

    A typo'd role silently promoted to the issuing role would hand a
    participant's deployment the ability to mint credentials — the exact
    outcome the split exists to prevent.
    """
    with pytest.raises(RoleConfigurationError):
        normalize_role(value)  # type: ignore[arg-type]


def test_the_role_setting_defaults_to_trust_anchor():
    """A deployment that says nothing keeps the behaviour it had."""
    assert Settings(_env_file=None).role == TRUST_ANCHOR


def test_router_names_are_unique():
    names = [spec.name for spec in ROUTERS]
    assert len(names) == len(set(names))


def test_every_router_is_served_by_some_role():
    for spec in ROUTERS:
        assert spec.roles, f"{spec.name} is mounted by no role"
        assert spec.roles <= roles.ROLES, f"{spec.name} names an unknown role"
