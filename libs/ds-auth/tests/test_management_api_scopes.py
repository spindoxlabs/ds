"""Only organisation clients hold EDC's management-API scopes.

EDC 0.18.0's OAuth2 filter checks a token's signature, issuer, `sub` and
`scope`, and **never its `aud`**. In a shared realm every client is therefore a
candidate caller of every participant's management API, and what stops that is
which clients hold a `management-api:*` scope. This file is the static half of
that rule; `tests/integration/test_organisation_clients.py` checks a realm.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ds_auth import (
    MANAGEMENT_API_SCOPES,
    ORGANISATION_CLIENT_PREFIX,
    ROLE_BUNDLES,
    SERVICE_ONLY_PERMISSIONS,
    all_bundled_permissions,
    is_management_api_scope,
    organisation_client_id,
    scope_satisfies,
)

REPO = Path(__file__).resolve().parents[3]
KEYCLOAK = REPO / "services" / "keycloak"

#: The resources EDC 0.18.0's v5 controllers name in `@RequiredScope`, read off
#: the v0.18.0 tag. A resource outside this set is a scope no controller checks.
EDC_V5_RESOURCES = frozenset(
    {
        "assets",
        "policies",
        "contractdefinitions",
        "negotiations",
        "agreements",
        "transfers",
        "catalog",
        "discovery",
        "profiles",
        "dataplanes",
    }
)


def _files() -> list[Path]:
    return sorted(KEYCLOAK.glob("clients*.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse(scope: str) -> tuple[str, str, str]:
    """EDC's `Scope.parse`: `prefix[:resource]:action`, resource default `*`."""
    parts = scope.split(":")
    assert 2 <= len(parts) <= 3 and all(parts), f"{scope!r} is not EDC grammar"
    resource = parts[1] if len(parts) == 3 else "*"
    return parts[0], resource, parts[-1]


def test_the_keycloak_files_are_where_we_think_they_are():
    assert (KEYCLOAK / "clients.yaml") in _files()


@pytest.mark.parametrize("scope", MANAGEMENT_API_SCOPES)
def test_every_granted_scope_is_edc_grammar_for_one_resource(scope):
    """Parsed as EDC parses it. A wildcard resource or the `admin` action would
    reach resources ds never calls, and `admin` ignores `sub` altogether."""
    prefix, resource, action = _parse(scope)
    assert prefix == "management-api"
    assert resource in EDC_V5_RESOURCES, (
        f"{scope}: no v5 controller checks {resource!r}"
    )
    assert action in {"read", "write"}, (
        f"{scope}: action {action!r} is not granted by ds"
    )


def test_the_list_has_no_duplicates_and_one_entry_per_resource():
    resources = [_parse(s)[1] for s in MANAGEMENT_API_SCOPES]
    assert len(resources) == len(set(resources))


def test_the_resume_route_scope_is_granted():
    """ds's own `NegotiationResumeController` requires `negotiations:write`."""
    assert "management-api:negotiations:write" in MANAGEMENT_API_SCOPES


def test_the_file_that_crosses_declares_exactly_the_granted_scopes():
    """Keycloak silently ignores a default scope that does not exist, so a
    granted scope the realm never declares is a client that looks provisioned
    and is refused by EDC. And a declared one ds never grants is vocabulary
    nobody should be handed."""
    declared = {
        s["name"]
        for s in _load(KEYCLOAK / "clients.yaml").get("scopes") or []
        if is_management_api_scope(s["name"])
    }
    assert declared == set(MANAGEMENT_API_SCOPES)


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_no_other_file_declares_a_management_api_scope(path):
    if path.name == "clients.yaml":
        pytest.skip("the one file that declares them")
    declared = [
        s["name"]
        for s in _load(path).get("scopes") or []
        if is_management_api_scope(s["name"])
    ]
    assert declared == [], f"{path.name} declares {declared}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_no_declared_client_holds_a_management_api_scope(path):
    """The sync provisions these clients; none of them is an organisation
    client, and none may act on a participant's management API."""
    held = {
        client["client_id"]: [
            s
            for s in (client.get("default_scopes") or [])
            + (client.get("optional_scopes") or [])
            if is_management_api_scope(s)
        ]
        for client in _load(path).get("clients") or []
    }
    offenders = {cid: scopes for cid, scopes in held.items() if scopes}
    assert offenders == {}, f"{path.name}: {offenders}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_no_declared_client_takes_the_organisation_client_prefix(path):
    """identity-registry owns that name space; a file declaring one would have
    its grants recomputed by the sync and its `sub` mapper left in place."""
    clashing = [
        c["client_id"]
        for c in _load(path).get("clients") or []
        if c["client_id"].startswith(ORGANISATION_CLIENT_PREFIX)
    ]
    assert clashing == []


def test_no_bundle_grants_a_management_api_scope():
    """A person reaches the organisation's connector through ds's routes, never
    EDC's management API."""
    assert not [p for p in all_bundled_permissions() if is_management_api_scope(p)]
    assert set(MANAGEMENT_API_SCOPES) <= SERVICE_ONLY_PERMISSIONS
    for bundle, capabilities in ROLE_BUNDLES.items():
        assert not any(is_management_api_scope(c) for c in capabilities), bundle


def test_the_namespace_check_matches_every_form():
    assert is_management_api_scope("management-api:admin")
    assert is_management_api_scope("management-api:*:write")
    assert is_management_api_scope("management-api")
    assert not is_management_api_scope("management-apis:read")
    assert not is_management_api_scope("connector.admin")


def test_the_organisation_client_id_is_the_svc_naming():
    assert organisation_client_id("example-rec") == "svc-ds-connector-example-rec"


# ── The matcher: EDC's `ScopeMatcher`, restated ──────────────────────────────


NEG = "management-api:negotiations"


@pytest.mark.parametrize(
    "granted,required,expected",
    [
        (
            ["management-api:negotiations:write"],
            "management-api:negotiations:read",
            True,
        ),
        (
            ["management-api:negotiations:read"],
            "management-api:negotiations:write",
            False,
        ),
        (["management-api:negotiations:write"], "management-api:transfers:read", False),
        (["management-api:*:read"], "management-api:transfers:read", True),
        (["management-api:read"], "management-api:transfers:read", True),
        (["management-api:admin"], "management-api:transfers:write", True),
        (["management-api:WRITE"], "management-api:assets:write", True),
        (["other-api:transfers:write"], "management-api:transfers:write", False),
        (["management-api:transfers"], "management-api:transfers:read", False),
        (["", "management-api::write"], "management-api:x:read", False),
        (["connector.admin"], "management-api:catalog:read", False),
        (["management-api:catalog:read"], "not a scope", False),
    ],
)
def test_the_matcher_follows_edc(granted, required, expected):
    assert scope_satisfies(granted, required) is expected


def test_an_organisation_client_may_ask_to_register_consent():
    """Plan `a-collector-registers-consent-at-the-holder`: the organisation's own
    client is the consent writer — at its own connector, or at a holder that
    accepts it as a collector. Which connector accepts it is the connector's
    decision; the scope only lets it ask."""
    from ds_auth import CONNECTOR_SERVICE_SCOPES, ORGANISATION_CLIENT_SCOPES

    assert "connector.consent.provision" in CONNECTOR_SERVICE_SCOPES
    assert "connector.consent.provision" in ORGANISATION_CLIENT_SCOPES
    # Never the cross-subject read beside it.
    assert "connector.consent.audience" not in ORGANISATION_CLIENT_SCOPES
