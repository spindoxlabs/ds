import time

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ds_auth import OidcConfig, Principal
from ds_auth.errors import PermissionDenied
from ds_auth.fastapi import require_permission


def _token(**claims):
    base = {"sub": "x", "iat": int(time.time()), "exp": int(time.time()) + 300}
    base.update(claims)
    return pyjwt.encode(base, "unused-in-insecure-dev", algorithm="HS256")


@pytest.fixture
def client():
    app = FastAPI()
    # insecure_dev so tests don't need a live Keycloak; auth logic is unchanged.
    app.state.oidc_config = OidcConfig(issuer_url=None, insecure_dev=True)

    def _same_participant(principal: Principal, request) -> bool:
        want = request.headers.get("X-Participant")
        if want and principal.claims.get("participant") != want:
            raise PermissionDenied("wrong participant")
        return True

    @app.get("/provider")
    async def provider(_p=Depends(require_permission("connector.provider.read"))):
        return {"ok": True}

    @app.get("/scoped")
    async def scoped(
        _p=Depends(require_permission("connector.admin", perimeter=_same_participant))
    ):
        return {"ok": True}

    return TestClient(app)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_service_token_scope_allows(client):
    tok = _token(
        preferred_username="service-account-svc-ds-portal",
        scope="connector.admin",
    )
    assert client.get("/provider", headers=_auth(tok)).status_code == 200


def test_user_token_group_allows(client):
    tok = _token(email="a@b.test", groups=["/connector.provider.read"])
    assert client.get("/provider", headers=_auth(tok)).status_code == 200


def test_user_without_group_denied(client):
    tok = _token(email="a@b.test", groups=["/some.other.group"])
    assert client.get("/provider", headers=_auth(tok)).status_code == 403


def test_user_scope_does_not_grant(client):
    # A user token carrying connector.admin only as an OIDC scope must NOT pass.
    tok = _token(email="a@b.test", scope="connector.admin", groups=[])
    assert client.get("/provider", headers=_auth(tok)).status_code == 403


def test_missing_token_401(client):
    assert client.get("/provider").status_code == 401


def test_perimeter_denies_cross_participant(client):
    tok = _token(
        preferred_username="service-account-svc",
        scope="connector.admin",
        participant="did:web:provider",
    )
    ok = client.get(
        "/scoped", headers={**_auth(tok), "X-Participant": "did:web:provider"}
    )
    assert ok.status_code == 200
    denied = client.get(
        "/scoped", headers={**_auth(tok), "X-Participant": "did:web:consumer"}
    )
    assert denied.status_code == 403


def test_unconfigured_app_returns_500():
    app = FastAPI()  # no app.state.oidc_config

    @app.get("/x")
    async def x(_p=Depends(require_permission("connector.admin"))):
        return {}

    tok = _token(scope="connector.admin", preferred_username="service-account-s")
    assert TestClient(app, raise_server_exceptions=False).get(
        "/x", headers=_auth(tok)
    ).status_code == 500
