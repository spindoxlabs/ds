import time

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ds_auth import OidcConfig, Principal
from ds_auth.errors import PermissionDenied
from ds_auth.fastapi import require_exact_permission, require_permission


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


# ── require_exact_permission — the admin superset must not apply ─────────────
#
# Some permissions mean "I am this component", not "I may administer it":
# accepting EDC webhook callbacks, reading the EDR signing keys. An operator
# holding connector.admin must not inherit them, or admin becomes the ability
# to forge a transfer-state callback and lift data-plane keys.


@pytest.fixture
def exact_client():
    app = FastAPI()
    app.state.oidc_config = OidcConfig(issuer_url=None, insecure_dev=True)

    @app.get("/webhook")
    async def webhook(_p=Depends(require_exact_permission("connector.webhook"))):
        return {"ok": True}

    return TestClient(app)


def test_exact_permission_allows_the_named_scope(exact_client):
    tok = _token(
        preferred_username="service-account-svc-edc", scope="connector.webhook"
    )
    assert exact_client.get("/webhook", headers=_auth(tok)).status_code == 200


def test_exact_permission_is_not_satisfied_by_admin(exact_client):
    """The whole point: connector.admin does not imply connector.webhook."""
    tok = _token(
        preferred_username="service-account-svc-ds-portal", scope="connector.admin"
    )
    assert exact_client.get("/webhook", headers=_auth(tok)).status_code == 403


def test_exact_permission_is_not_satisfied_by_admin_group(exact_client):
    """Same rule for a user token — an admin operator, not just an admin service."""
    tok = _token(email="admin@b.test", groups=["/connector.admin"])
    assert exact_client.get("/webhook", headers=_auth(tok)).status_code == 403


def test_exact_permission_allows_one_of_several(exact_client):
    tok = _token(
        preferred_username="service-account-svc-edc",
        scope="connector.webhook connector.provider.read",
    )
    assert exact_client.get("/webhook", headers=_auth(tok)).status_code == 200


def test_exact_permission_still_requires_a_token(exact_client):
    assert exact_client.get("/webhook").status_code == 401


def test_exact_permission_rejects_an_empty_permission_list():
    with pytest.raises(ValueError):
        require_exact_permission()
