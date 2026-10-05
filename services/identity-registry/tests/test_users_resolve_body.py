"""`POST /users/resolve` — the identifiers travel in the body, never in a URL.

An email or a username in a query string is recorded by every access log, proxy
and trace on the path. The query-string form stays for a compatibility window:
deprecated, logged without the identifier, and refused once the window closes.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from conftest import make_headers

from identity_registry.config import Settings
from identity_registry.db.models import Did, KeycloakMapping
from identity_registry.dependencies import get_settings_dep

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


def _settings(client, **values) -> None:
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", **values)
    client._transport.app.dependency_overrides[get_settings_dep] = lambda: settings


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


async def test_the_query_form_is_deprecated_and_logs_no_identifier(
    client, mapped, caplog
):
    caplog.set_level(logging.WARNING)
    r = await client.get(f"/users/resolve?email={EMAIL}", headers=RESOLVE)
    assert r.status_code == 200
    assert r.headers["Deprecation"] == "true"
    assert "Sunset" in r.headers
    assert "deprecated GET /users/resolve" in caplog.text
    assert "identifiers: email" in caplog.text
    assert EMAIL not in caplog.text and "person-a" not in caplog.text


async def test_the_query_form_can_be_switched_off(client, mapped):
    _settings(client, users_resolve_get=False)
    r = await client.get(f"/users/resolve?email={EMAIL}", headers=RESOLVE)
    assert r.status_code == 410
    assert "POST /users/resolve" in r.json()["detail"]
    # The body form is not affected.
    r = await client.post("/users/resolve", json={"email": EMAIL}, headers=RESOLVE)
    assert r.status_code == 200


def test_the_window_is_open_in_dev_whatever_the_date(monkeypatch):
    monkeypatch.setenv("DS_ENV", "dev")
    s = Settings(users_resolve_get_until=date(2020, 1, 1))
    assert s.users_resolve_get_allowed(today=date(2030, 1, 1))


def test_outside_dev_the_window_closes_on_its_date(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    s = Settings(users_resolve_get_until=date(2027, 1, 31))
    assert s.users_resolve_get_allowed(today=date(2027, 1, 31))
    assert not s.users_resolve_get_allowed(today=date(2027, 2, 1))


def test_an_explicit_setting_decides_in_any_environment(monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    after = date(2030, 1, 1)
    assert Settings(users_resolve_get=True).users_resolve_get_allowed(today=after)
    monkeypatch.setenv("DS_ENV", "dev")
    assert not Settings(users_resolve_get=False).users_resolve_get_allowed()
