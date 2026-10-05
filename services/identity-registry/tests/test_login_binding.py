"""GET /users/me — which subject is the person presenting this login?

The registry is the only place the link between a login and a subject DID is
stored, so a person route asks it before acting on a user credential
(`ds_auth.person_binding`) — with the person's own token, forwarded. The key is
the Keycloak user id within its realm, never the email, which moves.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from conftest import make_headers

from identity_registry.db.models import Did, KeycloakMapping

USER_DID = "did:web:rec.dataspaces.localhost:users:data-subject"
REALM = "dataspaces"
USER_ID = "00000000-0000-4000-a000-000000000004"


def person(sub: str = USER_ID, *, realm: str = REALM) -> dict:
    now = int(time.time())
    token = pyjwt.encode(
        {
            "iss": f"http://keycloak.test/realms/{realm}",
            "sub": sub,
            "email": "subject@example.test",
            "preferred_username": "subject@example.test",
            "iat": now,
            "exp": now + 300,
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed(db_session) -> None:
    db_session.add(Did(did=USER_DID, did_type="user", active=True))
    db_session.add(
        KeycloakMapping(
            did=USER_DID,
            keycloak_realm=REALM,
            keycloak_user_id=USER_ID,
            email="subject@example.test",
            subject_id=USER_DID,
        )
    )
    await db_session.commit()


@pytest.mark.rule("D-20")
async def test_a_login_learns_its_own_subject(client, db_session):
    await _seed(db_session)
    resp = await client.get("/users/me", headers=person())
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"did": USER_DID}


@pytest.mark.rule("D-20")
async def test_an_unmapped_login_is_bound_to_nobody(client, db_session):
    await _seed(db_session)
    resp = await client.get("/users/me", headers=person("someone-else"))
    assert resp.status_code == 404


@pytest.mark.rule("D-20")
async def test_the_same_user_id_from_another_realm_is_another_person(
    client, db_session
):
    await _seed(db_session)
    resp = await client.get("/users/me", headers=person(realm="elsewhere"))
    assert resp.status_code == 404


async def test_the_email_is_not_the_key(client, db_session):
    """Same address, different Keycloak user: a recycled or re-created account
    is not the person the mapping names."""
    await _seed(db_session)
    resp = await client.get("/users/me", headers=person("recreated-account"))
    assert resp.status_code == 404


@pytest.mark.rule("D-20")
async def test_a_service_token_names_no_person(client, db_session):
    """A service could otherwise ask about anyone it holds a token for —
    which is every person, since it holds only its own."""
    await _seed(db_session)
    resp = await client.get(
        "/users/me", headers=make_headers(scope="identity-registry.admin")
    )
    assert resp.status_code == 403


async def test_no_token_is_a_401(client, db_session):
    assert (await client.get("/users/me")).status_code == 401
