from ds_auth import Organization, Principal, extract_groups, is_service_account
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
