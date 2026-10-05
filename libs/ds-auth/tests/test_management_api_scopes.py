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
    decision; the scope only lets it ask — and since ADR-0026 it must **ask**:
    the grant is optional, so the default token the connector sends to every
    counterparty does not carry it."""
    from ds_auth import (
        CONNECTOR_SERVICE_SCOPES,
        ORGANISATION_CLIENT_OPTIONAL_SCOPES,
        ORGANISATION_CLIENT_SCOPES,
    )

    assert "connector.consent.provision" not in CONNECTOR_SERVICE_SCOPES
    assert "connector.consent.provision" in ORGANISATION_CLIENT_OPTIONAL_SCOPES
    assert "connector.consent.provision" in ORGANISATION_CLIENT_SCOPES
    # Never the cross-subject read beside it.
    assert "connector.consent.audience" not in ORGANISATION_CLIENT_SCOPES


def test_the_edc_scopes_and_the_acts_are_optional_and_the_service_scopes_default():
    """The organisation client's split: what every token carries, and what only
    a token that asks for it does — the connector's EDC token, and the
    organisation's own acts (ADR-0026)."""
    from ds_auth import (
        CONNECTOR_SERVICE_SCOPES,
        EDC_MANAGEMENT_SCOPE,
        ORGANISATION_ACTION_SCOPES,
        ORGANISATION_CLIENT_DEFAULT_SCOPES,
        ORGANISATION_CLIENT_OPTIONAL_SCOPES,
        ORGANISATION_CLIENT_SCOPES,
    )

    assert set(ORGANISATION_CLIENT_DEFAULT_SCOPES) == set(CONNECTOR_SERVICE_SCOPES)
    assert not any(
        is_management_api_scope(s) for s in ORGANISATION_CLIENT_DEFAULT_SCOPES
    )
    assert set(ORGANISATION_ACTION_SCOPES) == {
        "connector.consent.provision",
        "connector.consent.collector.read",
        "connector.provider.write",
    }
    assert not set(ORGANISATION_ACTION_SCOPES) & set(ORGANISATION_CLIENT_DEFAULT_SCOPES)
    assert set(ORGANISATION_CLIENT_OPTIONAL_SCOPES) == {
        *MANAGEMENT_API_SCOPES,
        EDC_MANAGEMENT_SCOPE,
        *ORGANISATION_ACTION_SCOPES,
    }
    assert set(ORGANISATION_CLIENT_SCOPES) == {
        *ORGANISATION_CLIENT_DEFAULT_SCOPES,
        *ORGANISATION_CLIENT_OPTIONAL_SCOPES,
    }
    # Nothing a counterparty could replay rides in the default token.
    assert "connector.provider.write" not in ORGANISATION_CLIENT_DEFAULT_SCOPES
    assert "identity-registry.memberships.write" not in ORGANISATION_CLIENT_SCOPES


def test_the_edc_token_scope_is_stated_not_every_optional_scope():
    """It used to join every optional scope; with the organisation's acts now
    optional too it would have carried consent and publishing into the token the
    connector hands its EDC. Pinned byte-for-byte, so no connector or EDC image
    change rides on this one."""
    from ds_auth import EDC_MANAGEMENT_SCOPE, EDC_TOKEN_SCOPE

    assert EDC_TOKEN_SCOPE == " ".join((*MANAGEMENT_API_SCOPES, EDC_MANAGEMENT_SCOPE))
    assert EDC_TOKEN_SCOPE == (
        "management-api:assets:write management-api:policies:write "
        "management-api:contractdefinitions:write management-api:catalog:read "
        "management-api:negotiations:write management-api:agreements:read "
        "management-api:transfers:write edc.management"
    )
    for act in (
        "connector.consent.provision",
        "connector.provider.write",
        "connector.consent.collector.read",
        "identity-registry.memberships.write",
    ):
        assert act not in EDC_TOKEN_SCOPE.split()


def test_the_collector_client_holds_no_default_and_no_edc_scope():
    """ADR-0026: whoever holds a collector secret holds no EDC power, and a token
    asked for nothing is accepted by no ds service."""
    from ds_auth import (
        COLLECTOR_CLIENT_DEFAULT_SCOPES,
        COLLECTOR_CLIENT_OPTIONAL_SCOPES,
        EDC_MANAGEMENT_SCOPE,
        collector_client_id,
    )

    assert COLLECTOR_CLIENT_DEFAULT_SCOPES == ()
    assert not any(is_management_api_scope(s) for s in COLLECTOR_CLIENT_OPTIONAL_SCOPES)
    assert EDC_MANAGEMENT_SCOPE not in COLLECTOR_CLIENT_OPTIONAL_SCOPES
    assert set(COLLECTOR_CLIENT_OPTIONAL_SCOPES) == {
        "identity-registry.memberships.write",
        "identity-registry.credentials.write",
        "connector.consent.provision",
        "connector.consent.collector.read",
        "connector.consent.audience",
        "connector.disclosure.record",
        "provenance.write",
        "identity-registry.keycloak.sync",
    }
    assert collector_client_id("example-rec") == "svc-ds-collector-example-rec"


def test_the_login_binding_is_a_collector_act_bound_to_the_registry():
    """ADR-0026, amended 2026-10-05: `keycloak.sync` binds a login to a DID of
    the organisation's own members, so it moved off the shared onboarding
    client onto the collector client, with the registry as its one audience;
    the plain client keeps it only as the dev transition."""
    from ds_auth import (
        COLLECTOR_CLIENT_OPTIONAL_SCOPES,
        IDENTITY_REGISTRY_AUDIENCE,
        KEYCLOAK_SYNC_SCOPE,
        ONBOARDING_TRANSITION_SCOPES,
        ORGANISATION_CLIENT_SCOPES,
        SCOPE_AUDIENCES,
    )

    assert KEYCLOAK_SYNC_SCOPE == "identity-registry.keycloak.sync"
    assert KEYCLOAK_SYNC_SCOPE in COLLECTOR_CLIENT_OPTIONAL_SCOPES
    assert SCOPE_AUDIENCES[KEYCLOAK_SYNC_SCOPE] == IDENTITY_REGISTRY_AUDIENCE
    assert KEYCLOAK_SYNC_SCOPE in ONBOARDING_TRANSITION_SCOPES
    # The connector's own client binds nobody's login.
    assert KEYCLOAK_SYNC_SCOPE not in ORGANISATION_CLIENT_SCOPES


def test_every_audience_bound_scope_is_declared_with_its_audience():
    """One audience per scope: requesting the scope is what makes its receiver
    accept the token. Declared in the file that crosses."""
    from ds_auth import SCOPE_AUDIENCES

    scopes = {
        s["name"]: s for s in _load(KEYCLOAK / "clients.yaml").get("scopes") or []
    }
    for scope, audience in SCOPE_AUDIENCES.items():
        assert scope in scopes, f"{scope} is not declared"
        assert scopes[scope].get("audience") == audience, scope


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name)
def test_no_declared_client_takes_the_collector_client_prefix(path):
    """identity-registry owns that name space too (org-sync, the bundle)."""
    from ds_auth import COLLECTOR_CLIENT_PREFIX

    clashing = [
        c["client_id"]
        for c in _load(path).get("clients") or []
        if c["client_id"].startswith(COLLECTOR_CLIENT_PREFIX)
    ]
    assert clashing == []


def test_the_edc_scope_carries_the_management_audience():
    """Declared in the file that crosses, with the audience the EDC filter requires."""
    from ds_auth import EDC_MANAGEMENT_AUDIENCE, EDC_MANAGEMENT_SCOPE

    scopes = {
        s["name"]: s for s in _load(KEYCLOAK / "clients.yaml").get("scopes") or []
    }
    assert scopes[EDC_MANAGEMENT_SCOPE].get("audience") == EDC_MANAGEMENT_AUDIENCE


def test_the_e2e_flow_requests_the_same_edc_scope():
    """ds-e2e does not depend on ds-auth, so it restates the scope string."""
    import ast as _ast

    from ds_auth import EDC_TOKEN_SCOPE

    flow = (
        REPO / "libs" / "ds-e2e" / "src" / "ds_e2e" / "flows" / "organisation_token.py"
    )
    tree = _ast.parse(flow.read_text(encoding="utf-8"))
    value = next(
        _ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, _ast.Assign)
        and any(getattr(t, "id", None) == "EDC_TOKEN_SCOPE" for t in node.targets)
    )
    assert value.split() == EDC_TOKEN_SCOPE.split()


def test_the_e2e_flows_request_the_same_consent_scopes():
    """ds-e2e restates the organisation's consent scopes (ADR-0026)."""
    import ast as _ast

    from ds_auth import CONSENT_COLLECTOR_READ_SCOPE, CONSENT_PROVISION_SCOPE

    module = REPO / "libs" / "ds-e2e" / "src" / "ds_e2e" / "consent.py"
    tree = _ast.parse(module.read_text(encoding="utf-8"))
    values = {
        t.id: _ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, _ast.Assign) and isinstance(node.value, _ast.Constant)
        for t in node.targets
        if isinstance(t, _ast.Name)
    }
    assert values["CONSENT_PROVISION_SCOPE"] == CONSENT_PROVISION_SCOPE
    assert values["CONSENT_COLLECTOR_READ_SCOPE"] == CONSENT_COLLECTOR_READ_SCOPE
