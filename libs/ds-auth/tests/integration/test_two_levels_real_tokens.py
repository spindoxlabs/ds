"""Two levels of authority, on tokens a real Keycloak issued.

The unit suite (`tests/test_two_levels.py`) holds `Principal` to a hand-written
case table. This holds it to **real** user tokens — signed by the realm, verified
through its JWKS by `verify_token`, and shaped by whatever mappers the realm
actually runs — for the three people the two-level model is about:

* a holder of the ``platform-admin`` realm role is the platform administrator,
  everywhere;
* an organisation's own administrator is **not** one, and holds nothing outside
  that organisation;
* a token that still carries a realm-level group (the retired model) gets
  nothing from it.

## Configuration

Defaults to ds's own dev realm (`DS_AUTH_TEST_ISSUER`, the users in
`services/keycloak/realm-dataspaces-dev.json` and `organizations.yaml`). Any other
local realm whose login client allows the password grant works too:

* `DS_AUTH_TEST_ISSUER` — the realm issuer (default: the ds dev realm);
* `DS_AUTH_USER_CLIENT_ID` / `DS_AUTH_USER_CLIENT_SECRET` — the login client
  (default `oauth2_proxy`, secret = client id);
* `DS_AUTH_USER_SCOPE` — default `openid email profile organization:*`, which
  lists every organisation of a multi-organisation user;
* `DS_AUTH_PLATFORM_ADMIN` — `user:password` holding `platform-admin`
  (default `admin@example.test:admin`);
* `DS_AUTH_ORG_ADMIN` — `user:password:alias`, an organisation's own admin
  (default `gridops@example.test:gridops:grid-operator`);
* `DS_AUTH_LEGACY_GROUP_TOKEN` — an access token that still carries a realm
  `groups` claim; that case skips without it.

Skips when the realm is unreachable; fails when it answers and refuses a user,
since that is a realm that does not match the configuration.
"""

from __future__ import annotations

import base64
import json
import os

import httpx
import pytest
from conftest import ISSUER

from ds_auth import OidcConfig, Principal, verify_token
from ds_auth.errors import TokenInvalid

pytestmark = [pytest.mark.integration, pytest.mark.rule("C-16", "C-17")]

TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"
CLIENT_ID = os.environ.get("DS_AUTH_USER_CLIENT_ID", "oauth2_proxy")
CLIENT_SECRET = os.environ.get("DS_AUTH_USER_CLIENT_SECRET", CLIENT_ID)
SCOPE = os.environ.get("DS_AUTH_USER_SCOPE", "openid email profile organization:*")
PLATFORM_ADMIN = os.environ.get("DS_AUTH_PLATFORM_ADMIN", "admin@example.test:admin")
ORG_ADMIN = os.environ.get(
    "DS_AUTH_ORG_ADMIN", "gridops@example.test:gridops:grid-operator"
)
LEGACY_TOKEN = os.environ.get("DS_AUTH_LEGACY_GROUP_TOKEN", "").strip()

#: An organisation alias nobody is a member of.
NOWHERE = "no-such-organisation-for-this-test"


def _password_token(username: str, password: str) -> str:
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "username": username,
                "password": password,
                "scope": SCOPE,
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        pytest.skip(f"Keycloak is not reachable at {TOKEN_URL}: {exc}")
    if response.status_code == 404 or response.status_code >= 500:
        pytest.skip(f"No realm at {TOKEN_URL} ({response.status_code})")
    assert response.status_code == 200, (
        f"{username} could not log in through {CLIENT_ID} "
        f"({response.status_code}): {response.text[:300]}"
    )
    return response.json()["access_token"]


def _verified(token: str) -> Principal:
    """Verified for real — signature against the realm's JWKS, issuer, expiry."""
    claims = verify_token(token, OidcConfig(issuer_url=ISSUER))
    return Principal.from_claims(claims)


def _unverified_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def test_the_platform_admin_role_is_the_platform_administrator():
    user, password = PLATFORM_ADMIN.split(":", 1)
    p = _verified(_password_token(user, password))

    assert not p.is_service
    assert "platform-admin" in p.realm_roles, p.realm_roles
    assert p.is_platform_admin
    assert p.grants("connector.admin")
    assert p.grants("identity-registry.admin")
    # Everywhere, member or not.
    assert p.grants_in(NOWHERE, "connector.provider.write")


def test_an_organisation_admin_is_not_a_platform_admin():
    user, password, alias = ORG_ADMIN.split(":", 2)
    p = _verified(_password_token(user, password))

    assert not p.is_service
    assert p.is_member_of(alias), (
        f"{user} carries no `organization.{alias}` claim — check the login "
        f"client emits organisations (scope {SCOPE!r})"
    )
    assert not p.is_platform_admin
    assert p.platform_authority == ()
    assert not p.grants("connector.admin")
    assert not p.grants("identity-registry.admin")
    assert not p.grants("identity-registry.organizations.read")
    # Whatever it holds, it holds inside its organisation only.
    assert p.authority_in(NOWHERE) == ()
    assert not p.grants_in(NOWHERE, "connector.provider.read")


def test_a_realm_group_still_in_a_token_grants_nothing():
    if not LEGACY_TOKEN:
        pytest.skip(
            "DS_AUTH_LEGACY_GROUP_TOKEN is unset: no token carrying a realm "
            "`groups` claim to test with (a converged realm cannot mint one)"
        )
    claims = _unverified_claims(LEGACY_TOKEN)
    groups = claims.get("groups")
    assert isinstance(groups, list) and groups, (
        "the fixture token carries no realm `groups` claim, so it cannot show "
        "that one grants nothing"
    )
    try:
        p = _verified(LEGACY_TOKEN)
    except TokenInvalid as exc:
        pytest.skip(f"the fixture token no longer verifies (expired?): {exc}")

    # The realm groups contribute nothing: authority is exactly what the token
    # would hold without them.
    without = Principal.from_claims(
        {k: v for k, v in p.claims.items() if k != "groups"}
    )
    assert p.authority == without.authority
    assert not p.is_platform_admin
    assert not p.grants("connector.admin")
    for group in groups:
        assert not p.grants(group.lstrip("/")), group
