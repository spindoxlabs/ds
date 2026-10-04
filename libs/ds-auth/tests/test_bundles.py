"""Role-bundle expansion — the user side of the authority vocabulary.

A person's bundles arrive on two levels (see `test_two_levels.py` for the shared
case table the portal also decides): a platform bundle from an allowlisted realm
role, an organisation bundle from a group inside one organisation. These tests pin
the expansion at each level plus the safety properties that make bundles usable at
all: a bundle can never confer a machine identity, an organisation group can never
reach a platform grant, and a realm-level group grants nothing.
"""

from ds_auth import (
    MACHINE_IDENTITY_PERMISSIONS,
    ROLE_BUNDLES,
    Principal,
    organisation_authority,
    platform_authority,
)

# ── An organisation bundle expands ───────────────────────────────────────────


def test_bundle_expands_to_its_capabilities():
    assert organisation_authority(["ds-participant-viewer"]) == (
        "connector.provider.read",
        "connector.history.read",
        "catalog.read",
        "provenance.read",
        "identity-registry.read",
    )


def test_two_bundles_union_without_duplicates():
    expanded = organisation_authority(["ds-participant-admin", "ds-participant-viewer"])
    assert len(expanded) == len(set(expanded))
    # Present in both bundles — must appear once, from the first.
    assert expanded.count("connector.provider.read") == 1


def test_expansion_preserves_first_seen_order():
    assert organisation_authority(["ds-participant-viewer", "ds-member"])[0] == (
        "connector.provider.read"
    )


def test_a_platform_role_expands_to_its_bundle():
    assert platform_authority(["platform-admin"]) == ROLE_BUNDLES["ds-admin"]
    assert (
        platform_authority(["ds-onboarding-operator"])
        == ROLE_BUNDLES["ds-onboarding-operator"]
    )


# ── Machine identity is never grantable to a person ──────────────────────────


def test_no_bundle_grants_a_machine_identity():
    """The property that makes `require_exact_permission` mean anything."""
    for name, capabilities in ROLE_BUNDLES.items():
        leaked = set(capabilities) & MACHINE_IDENTITY_PERMISSIONS
        assert not leaked, f"bundle {name} grants machine identity {leaked}"


def test_a_group_named_after_a_machine_identity_grants_nothing():
    """Naming a group `connector.internal` must not hand out the connector's own
    identity — however the realm was configured."""
    assert organisation_authority(["connector.internal"]) == ()
    assert organisation_authority(["connector.webhook"]) == ()
    assert platform_authority(["connector.internal"]) == ()


def test_machine_identity_is_dropped_but_siblings_survive():
    assert organisation_authority(["connector.internal", "provenance.read"]) == (
        "provenance.read",
    )


# ── No pass-through beyond the organisation vocabulary ───────────────────────


def test_an_organisation_permission_grants_itself():
    """A literal permission an organisation bundle already carries — the shape
    a host realm uses when it grants one scope to one organisation."""
    assert organisation_authority(["connector.provider.write"]) == (
        "connector.provider.write",
    )


def test_an_unknown_group_grants_nothing():
    """The old rule 3 let any group pass through as its own capability, which is
    how an organisation group named `connector.admin` became a deployment-wide
    grant. There is no migration to protect any more."""
    assert organisation_authority(["identity-registry.admin"]) == ()
    assert organisation_authority(["some.other.group"]) == ()


def test_empty_and_malformed_input():
    assert organisation_authority([]) == ()
    assert organisation_authority([""]) == ()
    assert organisation_authority([None, 42, "provenance.read"]) == ("provenance.read",)  # type: ignore[list-item]
    assert platform_authority([None, 42, "platform-admin"]) == ROLE_BUNDLES["ds-admin"]  # type: ignore[list-item]


# ── Through Principal, which is what call sites actually see ─────────────────


def _org_user(*groups: str, alias: str = "acme") -> Principal:
    return Principal.from_claims(
        {
            "sub": "u",
            "email": "u@example.test",
            "organization": {alias: {"groups": [f"/{g}" for g in groups]}},
        }
    )


def _platform_user(*roles: str) -> Principal:
    return Principal.from_claims(
        {"sub": "u", "email": "u@example.test", "realm_access": {"roles": list(roles)}}
    )


def _service(scopes: str) -> Principal:
    return Principal.from_claims(
        {"sub": "s", "preferred_username": "service-account-svc-x", "scope": scopes}
    )


def test_user_authority_is_expanded():
    assert _org_user("ds-participant-admin").grants("connector.provider.write")


def test_user_without_the_bundle_is_refused():
    assert not _org_user("ds-participant-viewer").grants("connector.provider.write")


def test_service_authority_is_not_expanded():
    """A bundle name in a `scope` claim means nothing — services enumerate."""
    assert not _service("ds-participant-admin").grants("connector.provider.write")
    assert _service("connector.provider.write").grants("connector.provider.write")


def test_platform_admin_reaches_a_service_through_the_superset():
    """`ds-admin` holds `connector.admin`, which satisfies any `connector.*`."""
    assert _platform_user("platform-admin").grants("connector.provider.write")
    assert _platform_user("platform-admin").grants("connector.registry.invalidate")


def test_platform_admin_still_cannot_be_a_machine():
    """`connector.admin` is a superset for `has_permission` and irrelevant to
    `has_exact_permission` — so the operator seat cannot become the connector."""
    admin = _platform_user("platform-admin")
    assert admin.grants("connector.internal")  # superset rule, non-exact
    assert not admin.grants_exactly(["connector.internal"])
    assert not admin.grants_exactly(["connector.webhook"])


def test_a_realm_group_grants_nothing():
    """Not `ds-admin`, not a bundle, not a permission — the top-level `groups`
    claim is never read for authority."""
    p = Principal.from_claims(
        {
            "sub": "u",
            "email": "u@example.test",
            "groups": ["/ds-admin", "ds-participant-admin", "connector.provider.write"],
        }
    )
    assert p.authority == ()
    assert not p.grants("catalog.read")


def test_an_organisation_group_cannot_be_a_platform_grant():
    p = _org_user("ds-admin", "ds-onboarding-operator", "connector.admin")
    assert p.authority == ()
    assert not p.grants("connector.admin")
    assert not p.grants("identity-registry.organizations.read")


# ── Per-organisation authority (grants_in) ───────────────────────────────────
#
# `grants` asks *what* a caller may do; `grants_in` asks *whose* data they may do
# it to. A read-only auditor for one participant who administers another must not
# report as an administrator everywhere — the one failure in this area that fails
# *open*, which is why these are the assertions that matter most.


def _multi_org(orgs: dict[str, list[str]], roles: list[str] | None = None) -> Principal:
    claims: dict = {
        "sub": "u",
        "email": "u@example.test",
        "organization": {a: {"groups": g} for a, g in orgs.items()},
    }
    if roles is not None:
        claims["realm_access"] = {"roles": roles}
    return Principal.from_claims(claims)


def test_org_groups_are_kept_per_organisation():
    principal = _multi_org({"acme": ["/ds-participant-admin"]})
    assert principal.get_organization("acme").groups == ("ds-participant-admin",)
    assert principal.authority_in("acme") == ROLE_BUNDLES["ds-participant-admin"]
    assert principal.authority_in("globex") == ()


def test_authority_is_confined_to_the_granting_organisation():
    """The fail-open case: admin in one org must not carry into another."""
    principal = _multi_org(
        {
            "acme": ["ds-participant-viewer"],
            "globex": ["ds-participant-admin"],
        },
    )
    assert principal.grants_in("globex", "connector.provider.write")
    assert not principal.grants_in("acme", "connector.provider.write")
    # The route-level answer is "somewhere", which is why owner-scoped
    # resources ask `grants_in` rather than derive it.
    assert principal.grants("connector.provider.write")


def test_read_still_works_where_only_read_was_granted():
    principal = _multi_org({"acme": ["ds-participant-viewer"]})
    assert principal.grants_in("acme", "connector.provider.read")


def test_non_membership_is_refused():
    principal = _multi_org({"acme": ["ds-participant-admin"]})
    assert not principal.grants_in("globex", "connector.provider.write")
    assert not principal.grants_in("", "connector.provider.write")


def test_a_platform_role_holds_in_every_organisation():
    """The platform level is valid everywhere, member or not."""
    principal = _multi_org({"acme": []}, roles=["platform-admin"])
    assert principal.grants_in("acme", "connector.provider.write")
    assert principal.grants_in("globex", "connector.provider.write")


def test_membership_alone_grants_nothing():
    """Being in an organisation is necessary, never sufficient."""
    principal = _multi_org({"acme": []})
    assert principal.is_member_of("acme")
    assert not principal.grants_in("acme", "connector.provider.write")


def test_machine_identity_is_unreachable_per_organisation_too():
    principal = _multi_org({"acme": ["ds-participant-admin"]}, roles=["platform-admin"])
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


def test_a_scope_named_org_group_holds_in_its_organisation_only():
    principal = _multi_org(
        {"acme": ["connector.provider.write"], "globex": ["ds-member"]}
    )
    assert principal.grants_in("acme", "connector.provider.write")
    assert not principal.grants_in("globex", "connector.provider.write")


# ── Layer B: a foreign IdP's organisation-group names → ds bundles ───────────
#
# Layer A (the bundle table) is ds's own semantics and lives in code. Layer B is
# about *someone else's* naming and therefore is deployment configuration — which
# is exactly why it must not be able to grant anything Layer A does not already
# define, nor lift an organisation group to the platform level.

# Imported here rather than at the top so it sits with the prose above that
# explains what Layer B is; `E402` is the price of keeping the two together.
from ds_auth import parse_group_aliases  # noqa: E402


def test_an_alias_translates_a_foreign_group():
    aliases = parse_group_aliases('{"celine-manager": "ds-participant-admin"}')
    assert (
        organisation_authority(["celine-manager"], aliases)
        == ROLE_BUNDLES["ds-participant-admin"]
    )


def test_an_alias_cannot_name_a_capability():
    """The whole point of the layer split: config may rename a role, never invent
    one. An alias pointing at a permission would make deployment configuration a
    permission table."""
    aliases = parse_group_aliases('{"sneaky": "connector.provider.write"}')
    assert aliases == {}
    assert organisation_authority(["sneaky"], aliases) == ()


def test_an_alias_cannot_name_a_platform_bundle():
    """That would make an organisation group a platform grant."""
    assert parse_group_aliases('{"host-admins": "ds-admin"}') == {}
    assert parse_group_aliases('{"host-ops": "ds-onboarding-operator"}') == {}


def test_an_alias_cannot_smuggle_in_a_machine_identity():
    assert parse_group_aliases('{"x": "connector.internal"}') == {}
    assert organisation_authority(["connector.internal"], {"y": "ds-member"}) == ()


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
        '{"good": "ds-member", "bad": "connector.admin", "also-bad": "ds-admin",'
        ' "also-good": "ds-participant-viewer"}'
    )
    assert aliases == {"good": "ds-member", "also-good": "ds-participant-viewer"}


def test_aliasing_does_not_shadow_a_native_bundle_name():
    """A ds bundle name still means itself even when aliases are configured."""
    aliases = parse_group_aliases('{"celine-manager": "ds-participant-admin"}')
    assert organisation_authority(["ds-member"], aliases) == ROLE_BUNDLES["ds-member"]


def test_aliases_never_apply_to_realm_roles():
    """Only `REALM_ROLE_BUNDLES` lifts a realm role to the platform level; the
    deployment's alias map cannot add to it."""
    principal = Principal.from_claims(
        {
            "sub": "u",
            "email": "u@example.test",
            "realm_access": {"roles": ["celine-manager"]},
        },
        group_aliases=parse_group_aliases('{"celine-manager": "ds-participant-admin"}'),
    )
    assert principal.authority == ()


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
    assert principal.grants("connector.provider.write")


def test_no_aliases_configured_changes_nothing():
    """The default path, and the one every existing deployment is on."""
    assert organisation_authority(["ds-member"], {}) == organisation_authority(
        ["ds-member"]
    )
    assert organisation_authority(["ds-member"], None) == organisation_authority(
        ["ds-member"]
    )


# ── Consent registration is an organisation's act, not an operator seat's ────
#
# Plan `a-collector-registers-consent-at-the-holder`, decision 5 (2026-09-17).
# A participant seat is not bound to a connector, so a participant operator
# holding `connector.consent.provision` could register consent at any connector,
# for any organisation's members.


def test_a_participant_operator_seat_cannot_register_consent():
    for seat in ("ds-participant-admin", "ds-participant-viewer", "ds-member"):
        assert "connector.consent.provision" not in ROLE_BUNDLES[seat], seat
        assert not _org_user(seat).grants("connector.consent.provision"), seat


def test_the_deployment_operator_still_reaches_it_through_the_superset():
    # `override_subject_withdrawal` is a person's act, and that person is the
    # platform administrator.
    assert _platform_user("platform-admin").grants("connector.consent.provision")


def test_consent_registration_is_classified_as_service_only():
    from ds_auth import SERVICE_ONLY_PERMISSIONS, all_bundled_permissions

    assert "connector.consent.provision" in SERVICE_ONLY_PERMISSIONS
    assert "connector.consent.provision" not in all_bundled_permissions()
    assert "identity-registry.collectors.write" in SERVICE_ONLY_PERMISSIONS
    assert "identity-registry.collectors.write" not in all_bundled_permissions()
