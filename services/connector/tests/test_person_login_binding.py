"""R3 — a person route acts for the person who logged in, not for whoever holds their credential.

A user credential is a bearer credential: the person holds no key, and any
service that can read it from the identity registry can present it. So every
route that accepts one now also takes the person's own Keycloak login token,
bound by the registry to the subject the credential names
(`ds_auth.person_binding`, ADR-0024).

Required unless `DS_ENV=dev` (this suite) or `CONNECTOR_PERSON_TOKEN_REQUIRED`
says otherwise, so the refusals here set the setting explicitly. Without it the
suite would be asserting the dev posture, which is the behaviour before R3.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.config import get_settings
from connector.db.engine import Base
from connector.dependencies import get_consumer_service, get_db, get_notifier, get_prov
from connector.main import create_app
from ds_auth.person_binding import LoginBindingUnavailable
from tests import make_headers, make_vc_headers

SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
REALM = "dataspaces"
ISSUER = f"http://keycloak.test/realms/{REALM}"
LOGIN = "00000000-0000-4000-a000-000000000004"
STRANGER = "00000000-0000-4000-a000-000000000099"

CONSUMER_DID = "did:web:third-party.dataspaces.localhost"
CONSUMER_SUBJECT = f"{CONSUMER_DID}:users:consumer-user"


def person_token(sub: str = LOGIN, *, iss: str = ISSUER) -> dict:
    """A human's access token, as oauth2-proxy forwards it: `sub` is the
    Keycloak user id, and there is an email — what marks it as a person."""
    now = int(time.time())
    token = pyjwt.encode(
        {
            "iss": iss,
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


class Registry:
    """The registry's binding, as `IdentityRegistryLoginBinding` asks it —
    with the person's own token, answering the DID that login is bound to."""

    def __init__(self, bindings: dict[tuple[str, str], str] | None = None):
        self.bindings = bindings or {(REALM, LOGIN): SUBJECT}
        self.asked: list[tuple[str, str]] = []
        self.tokens: list[str] = []
        self.down = False

    async def __call__(self, token: str, realm: str, user_id: str) -> str | None:
        self.asked.append((realm, user_id))
        self.tokens.append(token)
        if self.down:
            raise LoginBindingUnavailable("registry unreachable")
        return self.bindings.get((realm, user_id))


@pytest.fixture
def required(monkeypatch):
    monkeypatch.setattr(get_settings(), "person_token_required", True)


@pytest.fixture
def registry(client) -> Registry:
    registry = Registry()
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.login_binding = registry
    # Lifespan state the decision routes depend on; these tests are refused or
    # answered before either is used.
    app.dependency_overrides[get_notifier] = lambda: None
    app.dependency_overrides[get_prov] = lambda: None
    return registry


async def _my(client, headers: dict):
    return await client.get("/consent/my", headers=headers)


# ── required (every environment but dev) ──────────────────────────


@pytest.mark.rule("D-20")
async def test_a_credential_alone_is_refused(client, registry, required):
    """The whole of R3: the credential is what a service holds, not a login."""
    r = await _my(client, make_vc_headers())
    assert r.status_code == 401
    assert "login token" in r.json()["detail"]
    assert registry.asked == []


@pytest.mark.rule("D-20")
async def test_a_service_token_with_the_credential_is_refused(
    client, registry, required
):
    """What onboarding's member relay and ds-e2e sent: a service's own token
    plus the person's credential. A service is not the person."""
    r = await _my(client, {**make_vc_headers(), **make_headers(scope="connector.admin")})
    assert r.status_code == 403
    assert "service token" in r.json()["detail"]


@pytest.mark.rule("D-20")
async def test_the_persons_own_login_is_accepted(client, registry, required):
    headers = {**make_vc_headers(), **person_token()}
    r = await _my(client, headers)
    assert r.status_code == 200, r.text
    assert registry.asked == [(REALM, LOGIN)]
    # Asked with the person's token, not a service's.
    assert registry.tokens == [headers["Authorization"].removeprefix("Bearer ")]


@pytest.mark.rule("D-20")
async def test_somebody_elses_login_is_refused(client, registry, required):
    """A real, verified login — of another person — presenting this person's
    credential. The case a leaked credential plus any account produces."""
    r = await _my(client, {**make_vc_headers(), **person_token(STRANGER)})
    assert r.status_code == 403
    assert "does not belong" in r.json()["detail"]


async def test_the_realm_is_part_of_the_key(client, registry, required):
    """The same user id issued by another realm is another person."""
    r = await _my(
        client,
        {**make_vc_headers(), **person_token(iss="http://keycloak.test/realms/other")},
    )
    assert r.status_code == 403


async def test_a_registry_that_cannot_answer_is_a_503(client, registry, required):
    registry.down = True
    r = await _my(client, {**make_vc_headers(), **person_token()})
    assert r.status_code == 503


async def test_no_registry_to_ask_is_a_503(client, required):
    client._transport.app.state.login_binding = None  # type: ignore[attr-defined]
    r = await _my(client, {**make_vc_headers(), **person_token()})
    assert r.status_code == 503


async def test_a_token_that_does_not_verify_is_a_401(client, registry, required):
    r = await _my(client, {**make_vc_headers(), "Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


async def test_the_credential_is_still_checked_first(client, registry, required):
    """A login does not stand in for the credential: a mismatched subject
    header is the credential's refusal, before any binding is asked."""
    headers = {
        **make_vc_headers(),
        **person_token(),
        "X-Subject-Id": "did:web:rec.dataspaces.localhost:users:victim",
    }
    r = await _my(client, headers)
    assert r.status_code == 403
    assert registry.asked == []


@pytest.mark.rule("D-20")
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/consent/my/shares"),
        ("GET", "/consent/my/c-1"),
        ("POST", "/consent/my/c-1/approve"),
        ("POST", "/consent/my/c-1/reject"),
        ("POST", "/consent/my/c-1/revoke"),
        ("GET", "/consent/status?consumer_id=x&dataset_id=y&subject_id=" + SUBJECT),
    ],
)
async def test_every_person_route_takes_the_login(
    client, registry, required, method, path
):
    r = await client.request(method, path, headers=make_vc_headers())
    assert r.status_code == 401, (path, r.status_code, r.text)


async def test_sharing_a_decision_takes_the_login(client, registry, required):
    r = await client.post(
        "/consent/my/shares",
        json={"offer_id": "any", "enabled": True},
        headers=make_vc_headers(),
    )
    assert r.status_code == 401


# ── not required (DS_ENV=dev, or the transition switch) ───────────


async def test_in_dev_a_credential_alone_still_works(client, registry):
    """The pre-R3 behaviour, kept where nothing is at stake and for callers
    that have not moved yet (`CONNECTOR_PERSON_TOKEN_REQUIRED=false`)."""
    r = await _my(client, make_vc_headers())
    assert r.status_code == 200
    assert registry.asked == []


@pytest.mark.rule("D-20")
async def test_a_presented_login_is_always_bound(client, registry):
    """Not required is not "not checked": a login that is presented and
    belongs to somebody else is refused in dev too."""
    r = await _my(client, {**make_vc_headers(), **person_token(STRANGER)})
    assert r.status_code == 403


# ── /consumer/*: the credential branch takes the login too ────────


@pytest_asyncio.fixture
async def consumer_client(monkeypatch):
    monkeypatch.setenv("CONNECTOR_ROLE", "consumer")
    monkeypatch.setenv("CONNECTOR_CONSUMER_PARTICIPANT_DID", CONSUMER_DID)
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "person_token_required", True)

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    class _Consumer:
        class _prov:
            @staticmethod
            async def catalog_viewed(**kwargs):
                return None

        async def request_catalog(self, counter_party_address, counter_party_id=None):
            return {"dataset": []}

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_consumer_service] = lambda: _Consumer()
    app.state.login_binding = Registry({(REALM, LOGIN): CONSUMER_SUBJECT})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    await eng.dispose()
    get_settings.cache_clear()


def _consumer_vc() -> dict:
    return make_vc_headers(
        subject_did=CONSUMER_SUBJECT,
        role="ConsumerUser",
        linked_participant=CONSUMER_DID,
    )


@pytest.mark.rule("D-20")
async def test_the_consumer_routes_refuse_a_credential_alone(consumer_client):
    r = await consumer_client.get("/consumer/requests", headers=_consumer_vc())
    assert r.status_code == 401


@pytest.mark.rule("D-20", "C-19")
async def test_the_catalogue_refuses_a_credential_alone(consumer_client):
    body = {"counter_party_address": "http://provider.test/protocol/2025-1"}
    r = await consumer_client.post("/consumer/catalog", json=body, headers=_consumer_vc())
    assert r.status_code == 401
    r = await consumer_client.post(
        "/consumer/catalog", json=body, headers={**_consumer_vc(), **person_token()}
    )
    assert r.status_code == 200, r.text
