"""Role-bundle expansion — the user side of the authority vocabulary.

These tests pin the three rules in `expand_bundles` plus the two safety
properties that make bundles usable at all: a bundle can never confer a
machine identity, and a realm still carrying the old scope-named groups keeps
working unchanged.
"""
from ds_auth import (
    MACHINE_IDENTITY_PERMISSIONS,
    ROLE_BUNDLES,
    Principal,
    expand_bundles,
)

# ── Rule 1: a known bundle expands ───────────────────────────────────────────


def test_bundle_expands_to_its_capabilities():
    assert expand_bundles(["ds-participant-viewer"]) == (
        "connector.provider.read",
        "connector.history.read",
        "catalog.read",
        "provenance.read",
        "identity-registry.read",
    )


def test_two_bundles_union_without_duplicates():
    expanded = expand_bundles(["ds-participant-admin", "ds-participant-viewer"])
    assert len(expanded) == len(set(expanded))
    # Present in both bundles — must appear once, from the first.
    assert expanded.count("connector.provider.read") == 1


def test_expansion_preserves_first_seen_order():
    assert expand_bundles(["ds-participant-viewer", "ds-admin"])[0] == (
        "connector.provider.read"
    )


# ── Rule 2: machine identity is never grantable by group ─────────────────────


def test_no_bundle_grants_a_machine_identity():
    """The property that makes `require_exact_permission` mean anything."""
    for name, capabilities in ROLE_BUNDLES.items():
        leaked = set(capabilities) & MACHINE_IDENTITY_PERMISSIONS
        assert not leaked, f"bundle {name} grants machine identity {leaked}"


def test_a_group_named_after_a_machine_identity_is_dropped():
    """Naming a group `connector.internal` must not hand out the connector's own
    identity — however the realm was configured."""
    assert expand_bundles(["connector.internal"]) == ()
    assert expand_bundles(["connector.webhook"]) == ()


def test_machine_identity_is_dropped_but_siblings_survive():
    assert expand_bundles(["connector.internal", "provenance.read"]) == (
        "provenance.read",
    )


# ── Rule 3: pass-through keeps the current realm working ─────────────────────


def test_unknown_group_passes_through_as_itself():
    """This is the whole migration path: the ~30 scope-named groups still work."""
    assert expand_bundles(["connector.provider.write"]) == (
        "connector.provider.write",
    )


def test_bundles_and_legacy_groups_compose():
    expanded = expand_bundles(["ds-participant-viewer", "identity-registry.admin"])
    assert "identity-registry.admin" in expanded
    assert "connector.provider.read" in expanded


def test_empty_and_malformed_input():
    assert expand_bundles([]) == ()
    assert expand_bundles([""]) == ()
    assert expand_bundles([None, 42, "provenance.read"]) == ("provenance.read",)  # type: ignore[list-item]


# ── Through Principal, which is what call sites actually see ─────────────────


def _user(groups: list[str]) -> Principal:
    return Principal.from_claims(
        {"sub": "u", "email": "u@example.test", "groups": groups}
    )


def _service(scopes: str) -> Principal:
    return Principal.from_claims(
        {"sub": "s", "preferred_username": "service-account-svc-x", "scope": scopes}
    )


def test_user_authority_is_expanded():
    assert _user(["ds-participant-admin"]).grants("connector.provider.write")


def test_user_without_the_bundle_is_refused():
    assert not _user(["ds-participant-viewer"]).grants("connector.provider.write")


def test_service_authority_is_not_expanded():
    """A bundle name in a `scope` claim means nothing — services enumerate."""
    assert not _service("ds-participant-admin").grants("connector.provider.write")
    assert _service("connector.provider.write").grants("connector.provider.write")


def test_admin_bundle_reaches_a_service_through_the_superset():
    """`ds-admin` holds `connector.admin`, which satisfies any `connector.*`."""
    assert _user(["ds-admin"]).grants("connector.provider.write")
    assert _user(["ds-admin"]).grants("connector.registry.invalidate")


def test_admin_bundle_still_cannot_be_a_machine():
    """`connector.admin` is a superset for `has_permission` and irrelevant to
    `has_exact_permission` — so the operator seat cannot become the connector."""
    admin = _user(["ds-admin"])
    assert admin.grants("connector.internal")  # superset rule, non-exact
    assert not admin.grants_exactly(["connector.internal"])
    assert not admin.grants_exactly(["connector.webhook"])


def test_org_level_groups_expand_too():
    """Per-owner scoping rides on `organization.<alias>.groups`, so bundles have
    to expand there as well — that is what makes a bundle org-scopeable."""
    principal = Principal.from_claims(
        {
            "sub": "u",
            "email": "u@example.test",
            "organization": {"example-org": {"groups": ["ds-participant-admin"]}},
        }
    )
    assert principal.grants("connector.provider.write")
    assert principal.is_member_of("example-org")
