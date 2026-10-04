"""Two levels of authority, and nothing in between.

A person's authority comes from exactly two places:

* **platform** — a realm role in ``REALM_ROLE_BUNDLES`` (``platform-admin`` →
  ``ds-admin``), read from ``realm_access.roles`` only;
* **organisation** — a group inside one organisation, valid for that organisation.

A realm-level ``groups`` claim grants nothing; a role on another client grants
nothing; an organisation group cannot reach a platform bundle or a superset.

The case table in ``parity/authority-cases.json`` is also decided by the portal's
generated TypeScript (``services/portal/tests/unit/two-levels.test.ts``), so the
UI and the API cannot disagree about who may do what.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ds_auth import (
    MACHINE_IDENTITY_PERMISSIONS,
    ORGANISATION_BUNDLES,
    ORGANISATION_PERMISSIONS,
    PLATFORM_ADMIN_ROLE,
    PLATFORM_BUNDLES,
    REALM_ROLE_BUNDLES,
    ROLE_BUNDLES,
    Principal,
    extract_realm_roles,
    is_service_account,
    organisation_authority,
    parse_group_aliases,
    platform_authority,
)

CASES_FILE = Path(__file__).parent / "parity" / "authority-cases.json"
CASES = json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]


def _principal(case: dict) -> Principal:
    return Principal.from_claims(
        case["claims"], group_aliases=parse_group_aliases(case["aliases"])
    )


# ── The shared table ─────────────────────────────────────────────────────────


@pytest.mark.rule("C-16", "C-17")
@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_the_backend_decides_every_parity_case(case):
    p = _principal(case)
    expect = case["expect"]

    assert not p.is_service, "every parity case is a user token"
    assert p.is_platform_admin is expect["is_platform_admin"]
    assert ("connector.admin" in p.authority) is expect["operator"]
    assert set(p.platform_authority) == set(expect["platform"])
    assert set(p.authority) == set(expect["authority"])
    for perm, result in expect["grants"].items():
        assert p.grants(perm) is result, perm
    for check in expect["grants_in"]:
        assert p.grants_in(check["alias"], check["perm"]) is check["result"], check


def test_the_table_covers_the_four_cases_the_plan_names():
    names = " | ".join(c["name"] for c in CASES)
    for needle in (
        "admins member is not a platform admin",
        "platform-admin realm role holds everywhere",
        "realm group still present in a token grants nothing",
        "role on an unrelated client grants nothing",
    ):
        assert needle in names


# ── The table itself ─────────────────────────────────────────────────────────


def test_every_bundle_is_granted_at_exactly_one_level():
    assert PLATFORM_BUNDLES | ORGANISATION_BUNDLES == set(ROLE_BUNDLES)
    assert not PLATFORM_BUNDLES & ORGANISATION_BUNDLES


def test_a_realm_role_reaches_platform_bundles_only():
    assert set(REALM_ROLE_BUNDLES.values()) <= PLATFORM_BUNDLES
    assert REALM_ROLE_BUNDLES[PLATFORM_ADMIN_ROLE] == "ds-admin"
    assert PLATFORM_ADMIN_ROLE == "platform-admin"


def test_an_organisation_permission_is_never_a_superset_or_a_machine_identity():
    assert not [p for p in ORGANISATION_PERMISSIONS if p.endswith(".admin")]
    assert not ORGANISATION_PERMISSIONS & MACHINE_IDENTITY_PERMISSIONS


def test_no_organisation_permission_is_platform_only():
    """What only a platform bundle names stays out of every organisation's reach."""
    platform_only = {p for b in PLATFORM_BUNDLES for p in ROLE_BUNDLES[b]} - {
        p for b in ORGANISATION_BUNDLES for p in ROLE_BUNDLES[b]
    }
    assert platform_only, "the platform bundles must name something of their own"
    assert not platform_only & ORGANISATION_PERMISSIONS


# ── Reading the claim ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "claims, expected",
    [
        ({"realm_access": {"roles": ["a", "b", "a"]}}, ["a", "b"]),
        ({"realm_access": {"roles": ["a", 1, None, ""]}}, ["a"]),
        ({"realm_access": {"roles": "platform-admin"}}, []),
        ({"realm_access": ["platform-admin"]}, []),
        ({"roles": ["platform-admin"]}, []),
        ({"groups": ["platform-admin"]}, []),
        ({"resource_access": {"x": {"roles": ["platform-admin"]}}}, []),
        ({}, []),
    ],
)
def test_realm_roles_come_from_realm_access_only(claims, expected):
    assert extract_realm_roles(claims) == expected


def test_platform_authority_has_no_pass_through():
    assert platform_authority(["connector.admin", "ds-admin", "offline_access"]) == ()


def test_organisation_authority_drops_what_it_does_not_know():
    assert organisation_authority(["ds-admin", "connector.admin", "whatever"]) == ()
    assert organisation_authority(["ds-member", "catalog.read"]) == ("catalog.read",)


def test_an_alias_to_a_platform_bundle_is_dropped(caplog):
    aliases = parse_group_aliases(
        '{"host-admins": "ds-admin", "host-ops": "ds-onboarding-operator",'
        ' "host-managers": "ds-participant-admin"}'
    )
    assert aliases == {"host-managers": "ds-participant-admin"}
    assert "host-admins" in caplog.text and "host-ops" in caplog.text


# ── Services are not people ──────────────────────────────────────────────────


def test_a_service_never_gets_platform_authority_from_a_role():
    claims = {
        "sub": "svc",
        "azp": "svc-ds-publisher",
        "preferred_username": "service-account-svc-ds-publisher",
        "scope": "connector.provider.read",
        "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
    }
    p = Principal.from_claims(claims)
    assert p.is_service
    assert not p.is_platform_admin
    assert p.platform_authority == ()
    assert p.authority == ("connector.provider.read",)
    assert not p.grants("connector.admin")


def test_any_group_at_either_level_still_marks_a_human():
    """Classification is unchanged; it grants nothing by itself."""
    assert not is_service_account({"azp": "x", "groups": ["/anything"]})
    assert not is_service_account(
        {"azp": "x", "organization": {"o": {"groups": ["/viewers"]}}}
    )
    assert is_service_account({"azp": "x", "groups": ["/"]})
