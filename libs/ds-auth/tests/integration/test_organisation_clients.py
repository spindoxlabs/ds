"""In a provisioned realm, only organisation clients hold EDC's management-API
scopes, and their tokens name the organisation's participant context.

EDC 0.18.0's OAuth2 filter never checks `aud`, so any realm client holding a
`management-api:*` scope is a caller of some participant's management API. The
static half is `tests/test_management_api_scopes.py`; this asserts the realm the
two provisioning steps produce — `celine-policies keycloak sync` (the scopes)
and `ir-cli keycloak org-sync` (the organisation clients, with their `sub`).

Enumerating clients needs the realm's admin API: `KEYCLOAK_ADMIN_USERNAME` /
`KEYCLOAK_ADMIN_PASSWORD` (dev: `admin`/`admin`).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx
import pytest
import yaml
from conftest import ISSUER, declared_clients, fetch_token

from ds_auth import (
    MANAGEMENT_API_SCOPES,
    ORGANISATION_CLIENT_PREFIX,
    OidcConfig,
    is_management_api_scope,
    organisation_client_id,
    verify_token,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
ORGANIZATIONS = REPO_ROOT / "services" / "keycloak" / "organizations.yaml"
KEYCLOAK_URL, REALM = ISSUER.rsplit("/realms/", 1)
SUB_MAPPER = "participant-context-sub"


def _organisations() -> list[dict]:
    document = yaml.safe_load(ORGANIZATIONS.read_text(encoding="utf-8")) or {}
    return [
        o
        for o in document.get("organizations") or []
        if o.get("participant_context_id")
    ]


ORGS = _organisations()


def _payload(token: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==="))


@pytest.fixture(scope="module")
def admin(keycloak_is_up) -> httpx.Client:
    response = httpx.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin"),
            "password": os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin"),
        },
        timeout=10,
    )
    assert response.status_code == 200, (
        f"cannot administer the realm at {KEYCLOAK_URL} ({response.status_code}); "
        "set KEYCLOAK_ADMIN_USERNAME / KEYCLOAK_ADMIN_PASSWORD"
    )
    with httpx.Client(
        base_url=f"{KEYCLOAK_URL}/admin/realms/{REALM}",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        timeout=10,
    ) as client:
        yield client


def _held_management_scopes(admin: httpx.Client) -> dict[str, dict]:
    """clientId → {"scopes": management-api scopes held, "uuid": …}."""
    held: dict[str, dict] = {}
    for client in admin.get("/clients", params={"max": 1000}).json():
        names: set[str] = set()
        for kind in ("default-client-scopes", "optional-client-scopes"):
            names |= {
                s["name"] for s in admin.get(f"/clients/{client['id']}/{kind}").json()
            }
        mine = {n for n in names if is_management_api_scope(n)}
        if mine:
            held[client["clientId"]] = {"scopes": mine, "uuid": client["id"]}
    return held


def test_the_dev_declaration_names_organisation_clients():
    """Every assertion below is vacuous without one."""
    assert ORGS, f"no organisation with a participant_context_id in {ORGANIZATIONS}"


def test_only_organisation_clients_hold_a_management_api_scope(admin):
    held = _held_management_scopes(admin)
    assert held, (
        "no client holds a management-api scope — `ir-cli keycloak org-sync` "
        "was not run against this realm"
    )
    strangers = sorted(c for c in held if not c.startswith(ORGANISATION_CLIENT_PREFIX))
    assert strangers == [], (
        f"{strangers} hold EDC management-API scopes; EDC does not check `aud`, "
        "so each of them can act on a participant's management API"
    )


def test_no_client_holds_more_than_the_granted_list(admin):
    for client_id, entry in _held_management_scopes(admin).items():
        extra = entry["scopes"] - set(MANAGEMENT_API_SCOPES)
        assert not extra, f"{client_id} holds {sorted(extra)}"


def test_every_holder_names_its_participant_context(admin):
    """A holder without the `sub` mapper is refused by EDC at best, and at worst
    names a service-account UUID that happens to be a context id."""
    for client_id, entry in _held_management_scopes(admin).items():
        mappers = admin.get(f"/clients/{entry['uuid']}/protocol-mappers/models").json()
        subs = [
            m
            for m in mappers
            if m["name"] == SUB_MAPPER and m["config"].get("claim.name") == "sub"
        ]
        assert len(subs) == 1, f"{client_id} has {len(subs)} sub mappers"


def test_the_realm_declares_only_the_granted_management_api_scopes(admin):
    declared = {
        s["name"]
        for s in admin.get("/client-scopes").json()
        if is_management_api_scope(s["name"])
    }
    assert declared == set(MANAGEMENT_API_SCOPES)


@pytest.mark.parametrize("org", ORGS, ids=[o["alias"] for o in ORGS])
def test_an_organisation_token_carries_its_context_and_scopes(org, keycloak_is_up):
    token = fetch_token(organisation_client_id(org["alias"]))
    claims = _payload(token)
    assert claims["sub"] == org["participant_context_id"]
    assert set(MANAGEMENT_API_SCOPES) <= set(claims["scope"].split())
    # And ds's own services accept it: it is also the organisation connector's
    # identity towards them.
    verified = verify_token(
        token, OidcConfig(issuer_url=ISSUER, audience="svc-ds-connector")
    )
    assert verified["sub"] == org["participant_context_id"]


@pytest.mark.parametrize(
    "client", declared_clients(), ids=[c["client_id"] for c in declared_clients()]
)
def test_no_declared_client_token_carries_a_management_api_scope(
    client, keycloak_is_up
):
    scopes = set(_payload(fetch_token(client["client_id"])).get("scope", "").split())
    assert not [s for s in scopes if is_management_api_scope(s)]
