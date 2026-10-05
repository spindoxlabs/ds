"""`ds_auth.person_binding` — the login token, bound to the credential's subject (R3).

The route-level behaviour is asserted where the routes are (`services/connector`,
`services/provenance`); this covers the pieces they share: the realm read from
an issuer, the posture, and the registry client.
"""

from __future__ import annotations

import time

import httpx
import jwt as pyjwt
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from ds_auth import OidcConfig
from ds_auth.person_binding import (
    IdentityRegistryLoginBinding,
    LoginBindingUnavailable,
    bind_login_token,
    person_token_required,
    realm_of,
)

SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"


@pytest.mark.parametrize(
    ("issuer", "realm"),
    [
        ("https://keycloak.example/realms/dataspaces", "dataspaces"),
        ("https://keycloak.example/realms/dataspaces/", "dataspaces"),
        ("https://sso.example/auth/realms/host", "host"),
        ("https://keycloak.example/", None),
        ("", None),
        (None, None),
    ],
)
def test_the_realm_is_read_from_the_issuer(issuer, realm):
    assert realm_of(issuer) == realm


@pytest.mark.parametrize(
    ("env", "setting", "required"),
    [
        ("dev", None, False),
        ("production", None, True),
        ("staging", None, True),
        ("", None, True),
        ("dev", True, True),
        ("production", False, False),
    ],
)
def test_the_posture(monkeypatch, env, setting, required):
    monkeypatch.setenv("DS_ENV", env)
    assert person_token_required(setting) is required


def _registry(handler) -> IdentityRegistryLoginBinding:
    return IdentityRegistryLoginBinding(
        "http://ir.test", transport=httpx.MockTransport(handler)
    )


async def test_the_registry_is_asked_with_the_persons_token():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["Authorization"]))
        return httpx.Response(200, json={"did": SUBJECT})

    registry = _registry(handler)
    assert await registry("person-token", "dataspaces", "u-1") == SUBJECT
    assert seen == [("/users/me", "Bearer person-token")]


async def test_a_bound_login_is_cached_and_an_unbound_one_is_not():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(404)
        return httpx.Response(200, json={"did": SUBJECT})

    registry = _registry(handler)
    assert await registry("t", "dataspaces", "u-1") is None
    assert await registry("t", "dataspaces", "u-1") == SUBJECT
    assert await registry("t", "dataspaces", "u-1") == SUBJECT
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(403),
        httpx.Response(200, json={}),
        httpx.Response(200, content=b"not json"),
    ],
)
async def test_a_registry_that_cannot_answer_is_unavailable_not_unbound(response):
    registry = _registry(lambda request: response)
    with pytest.raises(LoginBindingUnavailable):
        await registry("t", "dataspaces", "u-1")


# ── bind_login_token, on a real request ───────────────────────────


def _token(**claims) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {"iat": now, "exp": now + 300, **claims}, "secret", algorithm="HS256"
    )


PERSON = {
    "iss": "https://keycloak.example/realms/dataspaces",
    "sub": "u-1",
    "email": "subject@example.test",
}
SERVICE = {"sub": "svc", "preferred_username": "service-account-svc-x", "scope": "x"}


def _app(lookup, *, required: bool) -> TestClient:
    app = FastAPI()
    config = OidcConfig(insecure_dev=True)

    @app.get("/")
    async def route(request: Request):
        try:
            return {
                "bound": await bind_login_token(
                    request, config, SUBJECT, lookup=lookup, required=required
                )
            }
        except HTTPException as exc:
            return {"status": exc.status_code, "detail": exc.detail}

    return TestClient(app)


class Lookup:
    def __init__(self, answer: str | None = SUBJECT):
        self.answer = answer
        self.calls = 0

    async def __call__(self, token, realm, user_id):
        self.calls += 1
        assert realm == "dataspaces"
        return self.answer


def _get(client: TestClient, claims: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {_token(**claims)}"} if claims else {}
    return client.get("/", headers=headers).json()


def test_required_and_absent_is_a_401():
    assert _get(_app(Lookup(), required=True))["status"] == 401


def test_required_and_a_service_token_is_a_403():
    assert _get(_app(Lookup(), required=True), SERVICE)["status"] == 403


def test_the_persons_own_login_binds():
    assert _get(_app(Lookup(), required=True), PERSON) == {"bound": "u-1"}


def test_somebody_elses_login_is_a_403_required_or_not():
    for required in (True, False):
        answer = _get(_app(Lookup("did:web:x:users:other"), required=required), PERSON)
        assert answer["status"] == 403


def test_a_login_bound_to_nobody_is_a_403():
    assert _get(_app(Lookup(None), required=True), PERSON)["status"] == 403


def test_not_required_accepts_no_token_and_a_service_token_without_asking():
    lookup = Lookup()
    assert _get(_app(lookup, required=False)) == {"bound": None}
    assert _get(_app(lookup, required=False), SERVICE) == {"bound": None}
    assert lookup.calls == 0


def test_no_registry_while_required_is_a_503():
    assert _get(_app(None, required=True), PERSON)["status"] == 503


def test_a_presented_token_that_does_not_verify_is_a_401_even_when_not_required():
    client = _app(Lookup(), required=False)
    expired = {**PERSON, "exp": int(time.time()) - 600, "iat": int(time.time()) - 900}
    headers = {"Authorization": f"Bearer {pyjwt.encode(expired, 'secret', algorithm='HS256')}"}
    assert client.get("/", headers=headers).json()["status"] == 401
