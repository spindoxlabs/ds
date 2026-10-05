"""`POST /users/resolve` — the identifiers travel in the body, never in a URL.

An email or a username in a query string is recorded by every access log, proxy
and trace on the path. The query-string form (`GET`) was withdrawn once no caller
used it: the path has no GET, so it answers 405 and the contract lists none.
"""

from __future__ import annotations

import pytest
from conftest import make_headers

from identity_registry.db.models import Did, KeycloakMapping

EMAIL = "person-a@example.test"
USER_DID = "did:web:rec.example.org:users:ex-00001"
RESOLVE = make_headers(scope="identity-registry.resolve")


@pytest.fixture
async def mapped(db_session):
    db_session.add(Did(did=USER_DID, did_type="user", active=True))
    db_session.add(
        KeycloakMapping(
            did=USER_DID,
            keycloak_realm="dataspaces",
            keycloak_user_id="kc-user-a",
            username="person-a",
            email=EMAIL,
            subject_id=USER_DID,
        )
    )
    await db_session.commit()


@pytest.mark.parametrize(
    "body",
    [
        {"email": EMAIL},
        {"username": "person-a"},
        {"realm": "dataspaces", "user_id": "kc-user-a"},
    ],
)
async def test_the_body_resolves_by_every_identifier(client, mapped, body):
    r = await client.post("/users/resolve", json=body, headers=RESOLVE)
    assert r.status_code == 200, r.text
    assert r.json()["did"] == USER_DID


async def test_the_body_answers_like_the_query_did(client, mapped):
    r = await client.post(
        "/users/resolve", json={"email": "x@example.test"}, headers=RESOLVE
    )
    assert r.status_code == 404
    r = await client.post("/users/resolve", json={}, headers=RESOLVE)
    assert r.status_code == 422


async def test_the_body_takes_no_unknown_field(client, mapped):
    """`derive` went with the query form: the registry derives no subject id, and
    the body refuses the field rather than ignoring it."""
    r = await client.post(
        "/users/resolve", json={"email": EMAIL, "derive": True}, headers=RESOLVE
    )
    assert r.status_code == 422


async def test_the_body_needs_the_resolve_permission(client, mapped):
    r = await client.post(
        "/users/resolve",
        json={"email": EMAIL},
        headers=make_headers(scope="identity-registry.read"),
    )
    assert r.status_code == 403


async def test_the_query_form_is_gone(client, mapped):
    r = await client.get(f"/users/resolve?email={EMAIL}", headers=RESOLVE)
    assert r.status_code == 405
    assert r.headers["allow"] == "POST"
    # The body form is not affected.
    r = await client.post("/users/resolve", json={"email": EMAIL}, headers=RESOLVE)
    assert r.status_code == 200


def test_the_contract_has_no_query_form(client):
    operations = client._transport.app.openapi()["paths"]["/users/resolve"]
    assert "get" not in operations
    assert "post" in operations
