import time

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ds_auth import OidcConfig, Principal
from ds_auth.errors import PermissionDenied
from ds_auth.fastapi import (
    PERMISSION_SCHEME_NAME,
    require_exact_permission,
    require_permission,
)


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


# ── E2E-03 · the route table has to describe itself ──────────────────────────
#
# `libs/ds-e2e`'s api-contract sweep probes every guarded route for refusal.
# Which routes those are was a hand-kept list in the harness, beside the routers
# it mirrored, and it had drifted to 70 of 110. The guard now publishes itself,
# so the sweep can be derived — and these pin both halves of that: the document
# says the right thing, and nothing about the request path changed.


def test_a_guarded_route_publishes_the_permissions_it_accepts(client):
    """The fact the sweep reads: guarded, and guarded by *what*.

    The permissions matter as much as the marker. The sweep replays every route
    with a deliberately under-privileged token, so it has to know which routes
    that token legitimately holds — and asking the route is the only way to stop
    that answer going stale, which is what happened to the hardcoded one.
    """
    spec = client.app.openapi()
    scheme = spec["components"]["securitySchemes"][PERMISSION_SCHEME_NAME]
    assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
    assert spec["paths"]["/provider"]["get"]["security"] == [
        {PERMISSION_SCHEME_NAME: ["connector.provider.read"]}
    ]
    assert spec["paths"]["/scoped"]["get"]["security"] == [
        {PERMISSION_SCHEME_NAME: ["connector.admin"]}
    ]


def test_require_exact_permission_publishes_itself_too(exact_client):
    """Both factories, or the sweep would read `/webhooks/*` as unguarded."""
    spec = exact_client.app.openapi()
    assert spec["paths"]["/webhook"]["get"]["security"] == [
        {PERMISSION_SCHEME_NAME: ["connector.webhook"]}
    ]


def test_an_unguarded_route_publishes_nothing():
    """The marker must mean something, so it must be absent where it should be."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    assert "security" not in app.openapi()["paths"]["/health"]["get"]
    assert "securitySchemes" not in app.openapi().get("components", {})


def test_publishing_the_scheme_changed_no_refusal(client):
    """`auto_error=False`, so the scheme never decides anything.

    It is declared to make the route table self-describing and for no other
    reason. If it ever started answering, an absent or malformed credential
    would come back 403 (its own default) instead of the 401 `authenticate`
    produces, and every caller distinguishing "who are you" from "you may not"
    would silently change meaning.
    """
    assert client.get("/provider").status_code == 401
    basic = client.get("/provider", headers={"Authorization": "Basic x"})
    assert basic.status_code == 401
    assert client.get("/provider", headers=_auth("not-a-jwt")).status_code == 401
