from ds_auth import Principal, extract_groups, is_service_account
from ds_auth.jwt import extract_scopes


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
