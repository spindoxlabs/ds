"""R3 — `GET /prov/my/events` is read by the person who logged in.

The credential alone is a bearer credential any service that reads it from the
identity registry can present. So the route also takes the person's own login
token, which the registry binds to the subject the credential names
(`ds_auth.person_binding`, ADR-0024). Required unless `DS_ENV=dev` (this suite)
or `PROVENANCE_PERSON_TOKEN_REQUIRED` says otherwise — so the refusals set it.
"""

from __future__ import annotations

import base64
import json
import time

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from provenance.config import get_settings
from provenance.dependencies import get_db
from provenance.main import create_app

from tests import make_headers

SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
REALM = "dataspaces"
LOGIN = "00000000-0000-4000-a000-000000000004"


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def vc_headers(subject: str = SUBJECT) -> dict:
    """A well-formed credential; the suite runs with `VC_INSECURE_DEV` (no
    signature check), every other claim is still checked."""
    payload = {
        "iss": "did:web:trust-anchor.dataspaces.localhost",
        "sub": subject,
        "exp": int(time.time()) + 3600,
        "vc": {
            "issuer": "did:web:trust-anchor.dataspaces.localhost",
            "credentialSubject": {"id": subject, "role": "DataSubject"},
        },
    }
    token = ".".join(
        (_b64(json.dumps({"alg": "ES256"})), _b64(json.dumps(payload)), _b64("x"))
    )
    return {"X-Subject-Id": subject, "X-User-VC": token}


def login(sub: str = LOGIN) -> dict:
    now = int(time.time())
    token = pyjwt.encode(
        {
            "iss": f"http://keycloak.test/realms/{REALM}",
            "sub": sub,
            "email": "subject@example.test",
            "iat": now,
            "exp": now + 300,
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class Registry:
    def __init__(self):
        self.bindings = {(REALM, LOGIN): SUBJECT}

    async def __call__(self, token, realm, user_id):
        return self.bindings.get((realm, user_id))


@pytest_asyncio.fixture
async def person_client(engine, monkeypatch):
    """No default service headers: this route is a person's, not a scope's."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.state.login_binding = Registry()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def required(monkeypatch):
    monkeypatch.setattr(get_settings(), "person_token_required", True)


@pytest.mark.rule("D-20", "L-11")
@pytest.mark.asyncio
async def test_a_credential_alone_is_refused(person_client, required):
    r = await person_client.get("/prov/my/events", headers=vc_headers())
    assert r.status_code == 401


@pytest.mark.rule("D-20", "L-11")
@pytest.mark.asyncio
async def test_a_service_token_with_the_credential_is_refused(person_client, required):
    r = await person_client.get(
        "/prov/my/events",
        headers={**vc_headers(), **make_headers(scope="provenance.read")},
    )
    assert r.status_code == 403


@pytest.mark.rule("D-20", "L-11")
@pytest.mark.asyncio
async def test_the_persons_own_login_reads_their_history(person_client, required):
    r = await person_client.get("/prov/my/events", headers={**vc_headers(), **login()})
    assert r.status_code == 200, r.text


@pytest.mark.rule("D-20", "L-11")
@pytest.mark.asyncio
async def test_somebody_elses_login_is_refused(person_client, required):
    r = await person_client.get(
        "/prov/my/events", headers={**vc_headers(), **login("someone-else")}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_in_dev_the_credential_alone_still_reads(person_client):
    r = await person_client.get("/prov/my/events", headers=vc_headers())
    assert r.status_code == 200, r.text
