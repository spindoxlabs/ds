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


# ── Per-organisation authority (grants_in) ───────────────────────────────────
#
# `grants` asks *what* a caller may do; `grants_in` asks *whose* data they may do
# it to. Before it existed the second question could not be asked at all:
# `extract_groups` flattens every organisation's groups into one list, so a
# read-only auditor for one participant who administers another reported as an
# administrator everywhere. That is the one failure in this area that failed
# *open*, which is why these are the assertions that matter most.


def _multi_org(realm: list[str], orgs: dict[str, list[str]]) -> Principal:
    return Principal.from_claims(
        {
            "sub": "u",
            "email": "u@example.test",
            "groups": realm,
            "organization": {a: {"groups": g} for a, g in orgs.items()},
        }
    )


def test_org_groups_are_no_longer_discarded():
    principal = _multi_org([], {"acme": ["ds-participant-admin"]})
    assert principal.get_organization("acme").groups == ("ds-participant-admin",)


def test_authority_is_confined_to_the_granting_organisation():
    """The fail-open case: admin in one org must not carry into another."""
    principal = _multi_org(
        [],
        {
            "acme": ["ds-participant-viewer"],
            "globex": ["ds-participant-admin"],
        },
    )
    assert principal.grants_in("globex", "connector.provider.write")
    assert not principal.grants_in("acme", "connector.provider.write")
    # Flattened authority still reports the write — which is exactly why the
    # per-organisation question had to be asked separately rather than derived.
    assert principal.grants("connector.provider.write")


def test_read_still_works_where_only_read_was_granted():
    principal = _multi_org([], {"acme": ["ds-participant-viewer"]})
    assert principal.grants_in("acme", "connector.provider.read")


def test_non_membership_is_refused():
    principal = _multi_org([], {"acme": ["ds-participant-admin"]})
    assert not principal.grants_in("globex", "connector.provider.write")
    assert not principal.grants_in("", "connector.provider.write")


def test_realm_groups_are_deployment_wide():
    """A realm-level grant is not organisation-scoped, and must not be treated as
    if it were: a single-participant deployment legitimately grants at realm level
    and models no organisations at all."""
    principal = _multi_org(["ds-participant-admin"], {"acme": []})
    assert principal.grants_in("acme", "connector.provider.write")


def test_realm_admin_bundle_reaches_a_member_organisation():
    principal = _multi_org(["ds-admin"], {"acme": []})
    assert principal.grants_in("acme", "connector.provider.write")


def test_membership_alone_grants_nothing():
    """Being in an organisation is necessary, never sufficient."""
    principal = _multi_org([], {"acme": []})
    assert principal.is_member_of("acme")
    assert not principal.grants_in("acme", "connector.provider.write")


def test_machine_identity_is_unreachable_per_organisation_too():
    principal = _multi_org(["ds-admin"], {"acme": ["ds-participant-admin"]})
    # The superset rule applies to `grants_in` as it does to `grants`…
    assert principal.grants_in("acme", "connector.internal")
    # …and `grants_exactly` remains the guard that actually protects it.
    assert not principal.grants_exactly(["connector.internal"])


def test_a_service_has_no_per_organisation_authority():
    """Services authorise on scopes and carry no organisations. Call sites that
    must let them through check `is_service` explicitly, so the exemption is
    visible where it is granted."""
    service = Principal.from_claims(
        {
            "sub": "s",
            "preferred_username": "service-account-svc-ds-portal",
            "scope": "connector.provider.write",
        }
    )
    assert service.grants("connector.provider.write")
    assert not service.grants_in("acme", "connector.provider.write")


def test_legacy_scope_named_org_group_still_works():
    """Pass-through applies inside an organisation too, so a realm carrying the
    old scope-named groups keeps authorising during migration."""
    principal = _multi_org([], {"acme": ["connector.provider.write"]})
    assert principal.grants_in("acme", "connector.provider.write")


# ── Layer B: a foreign IdP's group names → ds bundles ────────────────────────
#
# Layer A (the bundle table) is ds's own semantics and lives in code. Layer B is
# about *someone else's* naming and therefore is deployment configuration — which
# is exactly why it must not be able to grant anything Layer A does not already
# define. These tests are that boundary.

from ds_auth import parse_group_aliases


def test_an_alias_translates_a_foreign_group():
    aliases = parse_group_aliases('{"celine-manager": "ds-participant-admin"}')
    assert expand_bundles(["celine-manager"], aliases) == ROLE_BUNDLES[
        "ds-participant-admin"
    ]


def test_an_alias_cannot_name_a_capability():
    """The whole point of the layer split: config may rename a role, never invent
    one. An alias pointing at a permission would make deployment configuration a
    permission table."""
    aliases = parse_group_aliases('{"sneaky": "connector.provider.write"}')
    assert aliases == {}
    # And the group then falls through to pass-through, granting only itself —
    # which matches a call site only if that call site asked for "sneaky".
    assert expand_bundles(["sneaky"], aliases) == ("sneaky",)


def test_an_alias_cannot_smuggle_in_a_machine_identity():
    """Rule 2 is applied *after* translation, so neither route reaches it."""
    assert parse_group_aliases('{"x": "connector.internal"}') == {}
    assert expand_bundles(["connector.internal"], {"y": "ds-admin"}) == ()


def test_an_alias_to_an_unknown_bundle_is_dropped():
    assert parse_group_aliases('{"x": "ds-does-not-exist"}') == {}


def test_malformed_alias_config_is_empty_not_partial():
    """A typo must not silently become a *different* map."""
    assert parse_group_aliases("not json") == {}
    assert parse_group_aliases('["a", "b"]') == {}
    assert parse_group_aliases('{"a": 1}') == {}
    assert parse_group_aliases("") == {}
    assert parse_group_aliases(None) == {}


def test_valid_entries_survive_alongside_invalid_ones():
    aliases = parse_group_aliases(
        '{"good": "ds-member", "bad": "connector.admin", "also-good": "ds-admin"}'
    )
    assert aliases == {"good": "ds-member", "also-good": "ds-admin"}


def test_aliasing_does_not_shadow_a_native_bundle_name():
    """A ds bundle name still means itself even when aliases are configured."""
    aliases = parse_group_aliases('{"celine-manager": "ds-participant-admin"}')
    assert expand_bundles(["ds-member"], aliases) == ROLE_BUNDLES["ds-member"]


def test_aliases_apply_to_per_organisation_authority_too():
    """`authority` and `grants_in` must not disagree about what a foreign name
    means — the alias map is carried on the Principal for that reason."""
    principal = Principal.from_claims(
        {
            "sub": "u",
            "email": "u@example.test",
            "organization": {
                "acme": {"groups": ["celine-manager"]},
                "globex": {"groups": ["celine-viewer"]},
            },
        },
        group_aliases=parse_group_aliases(
            '{"celine-manager": "ds-participant-admin",'
            ' "celine-viewer": "ds-participant-viewer"}'
        ),
    )
    assert principal.grants_in("acme", "connector.provider.write")
    assert not principal.grants_in("globex", "connector.provider.write")
    assert principal.grants_in("globex", "connector.provider.read")


def test_no_aliases_configured_changes_nothing():
    """The default path, and the one every existing deployment is on."""
    assert expand_bundles(["ds-admin"], {}) == expand_bundles(["ds-admin"])
    assert expand_bundles(["ds-admin"], None) == expand_bundles(["ds-admin"])
