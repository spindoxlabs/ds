import logging

from ds_auth import Principal, extract_groups, is_service_account
from ds_auth.jwt import extract_organizations, extract_scopes


def test_extract_groups_realm_and_org():
    claims = {
        "groups": ["/ds-admin", "managers"],
        "organization": {
            "acme": {"groups": ["/viewers"]},
            "other": {"groups": ["managers"]},  # dup across sources
        },
    }
    assert extract_groups(claims) == ["ds-admin", "managers", "viewers"]


def test_extract_groups_absent():
    assert extract_groups({}) == []


def test_extract_scopes_string_and_list():
    assert extract_scopes({"scope": "a b c"}) == ["a", "b", "c"]
    assert extract_scopes({"scope": ["a", "b"]}) == ["a", "b"]
    assert extract_scopes({}) == []


def test_is_service_account_preferred_username():
    assert is_service_account({"preferred_username": "service-account-svc-ds-portal"})


def test_is_service_account_gty():
    assert is_service_account({"gty": "client-credentials", "client_id": "svc"})


def test_user_is_not_service_account():
    assert not is_service_account(
        {"preferred_username": "alice", "email": "alice@example.test"}
    )
    assert not is_service_account({"groups": ["/ds-admin"]})


# ── AUTH-02 · what a bare `scope` claim does and does not prove ──────────────
#
# The ledger carried a row asking for `{scope, sub}` to be read as a service
# account. It must not be, and the tests below are the reason written down: the
# claim is on *both* kinds of token, so the change trades two red fixtures for a
# collapsed authorization model. See the docstring on `is_service_account` and
# `services/federated-catalog/tests/test_auth.py`.


def test_a_real_keycloak_service_token_is_classified_correctly():
    """What a client-credentials grant actually looks like.

    All three signals present. This is what the four fixtures that made the row
    look real were missing.
    """
    assert is_service_account({
        "sub": "b2c3",
        "scope": "catalog.read",
        "azp": "svc-ds-federated-catalog",
        "client_id": "svc-ds-federated-catalog",
        "preferred_username": "service-account-svc-ds-federated-catalog",
    })


def test_a_service_token_with_only_azp_is_still_classified_correctly():
    """A realm whose default scopes lack the username/client_id mappers —
    clients provisioned by the `celine-policies` sync."""
    assert is_service_account({"sub": "b2c3", "scope": "catalog.read", "azp": "svc-x"})


def test_a_human_token_carries_scope_too_and_is_still_a_user():
    """The counterfactual for the change the row asked for.

    Keycloak puts `openid profile email` on every human token. Reading `scope`
    as proof of a service would make this user a service account, and then
    authorize them on OIDC scopes instead of on their group membership.
    """
    claims = {
        "sub": "a1b2",
        "scope": "openid profile email",
        "preferred_username": "alice",
        "email": "alice@example.test",
        "groups": ["/ds-member"],
    }
    assert not is_service_account(claims)
    assert Principal.from_claims(claims).is_service is False


def test_a_token_with_no_indicator_either_way_is_a_user_and_says_so(caplog):
    """The residue of the row: a token Keycloak does not issue.

    Classified as a user — the closed direction, since a user with no groups
    grants nothing — and logged, because otherwise the 403 that follows names a
    permission and nothing about why the scope was never consulted.
    """
    claims = {"sub": "unknown", "scope": "catalog.read"}
    with caplog.at_level(logging.WARNING, logger="ds_auth.jwt"):
        assert not is_service_account(claims)
    assert "no service-account indicator" in caplog.text
    assert "catalog.read" in caplog.text


def test_an_ordinary_user_token_does_not_produce_that_warning(caplog):
    """Or the log fills with it on every request and stops being read."""
    with caplog.at_level(logging.WARNING, logger="ds_auth.jwt"):
        is_service_account({
            "sub": "a1b2", "scope": "openid profile", "email": "alice@example.test",
        })
    assert caplog.text == ""


def test_a_scopeless_token_produces_no_warning_either(caplog):
    with caplog.at_level(logging.WARNING, logger="ds_auth.jwt"):
        is_service_account({"sub": "a1b2"})
    assert caplog.text == ""


def test_principal_service_authorizes_on_scopes():
    p = Principal.from_claims(
        {
            "preferred_username": "service-account-svc-ds-portal",
            "scope": "connector.admin provenance.read",
        }
    )
    assert p.is_service
    assert p.authority == ("connector.admin", "provenance.read")
    assert p.grants("connector.provider.write")  # via connector.admin superset
    assert not p.grants("dataset.admin")


def test_principal_user_authorizes_on_groups():
    p = Principal.from_claims(
        {
            "sub": "u-1",
            "email": "alice@example.test",
            "groups": ["/connector.provider.write"],
            # A user's scope claim (openid/profile) must NOT grant permissions.
            "scope": "openid profile email",
        }
    )
    assert not p.is_service
    assert p.authority == ("connector.provider.write",)
    assert p.grants("connector.provider.write")
    assert not p.grants("connector.admin")
    # The OIDC scopes on the user token confer no permission.
    assert not p.grants("openid")


# ── Organization parsing ─────────────────────────────────────────────────────


def test_extract_organizations_from_claim():
    claims = {
        "organization": {
            "example-dso": {
                "type": ["dso"],
                "attributes": {"region": ["EU"]},
                "groups": ["admins"],
            },
            "example-rec": {
                "type": ["rec"],
                "groups": ["viewers"],
            },
        },
    }
    orgs = extract_organizations(claims)
    assert len(orgs) == 2

    dso = next(o for o in orgs if o.alias == "example-dso")
    assert dso.type == "dso"
    assert dso.attributes == {"region": ["EU"]}
    assert dso.is_type("dso")
    assert dso.has_attribute("region", "EU")
    assert dso.get_attribute("region") == ["EU"]

    rec = next(o for o in orgs if o.alias == "example-rec")
    assert rec.type == "rec"
    assert rec.attributes == {}


def test_extract_organizations_empty():
    assert extract_organizations({}) == []
    assert extract_organizations({"organization": "not-a-dict"}) == []


def test_principal_organizations():
    claims = {
        "sub": "u-1",
        "email": "alice@example.test",
        "organization": {
            "acme": {"type": ["dso"], "groups": ["/admins"]},
            "other": {"groups": ["viewers"]},
        },
    }
    p = Principal.from_claims(claims)
    assert p.organization_aliases == ["acme", "other"]
    assert p.is_member_of("acme")
    assert not p.is_member_of("unknown")
    assert p.get_organization("acme") is not None
    assert p.get_organization("acme").type == "dso"
    assert p.get_organization("unknown") is None


def test_extract_groups_ignores_org_roles():
    """Org roles are NOT emitted by the KC organization membership mapper."""
    claims = {
        "organization": {
            "org1": {"groups": ["admins"], "roles": ["should-be-ignored"]},
        },
    }
    groups = extract_groups(claims)
    assert "admins" in groups
    assert "should-be-ignored" not in groups
