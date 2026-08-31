import time

import httpx
import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from identity_registry.config import Settings
from identity_registry.db.engine import Base
from identity_registry.dependencies import get_db, get_did_resolver, get_settings_dep
from identity_registry.main import create_app
from identity_registry.services.did import build_did_document
from identity_registry.services.did_resolver import DidResolutionError

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def make_headers(scope: str = "identity-registry.admin") -> dict:
    # `exp` is not decoration. `ds_auth.verify_token` checks expiry even with no
    # issuer configured — signature and audience are the only checks the
    # `insecure_dev` path skips — so a token without it is refused, and Keycloak
    # has never minted one.
    now = int(time.time())
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "test",
            "preferred_username": "service-account-svc-ds-identity-registry",
            "iat": now,
            "exp": now + 300,
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


make_admin_headers = make_headers


@pytest_asyncio.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


class StubResolver:
    """Serves DID documents from a dict instead of over HTTP.

    The production resolver always goes through did:web — deliberately, so dev
    and production run the same code — which means a unit test has to supply the
    documents. Registering one here is the test's way of saying "this DID is
    published, with this key".
    """

    def __init__(self, documents: dict[str, dict] | None = None):
        self.documents = documents or {}

    def publish(self, did: str, public_jwk: dict) -> None:
        self.documents[did] = build_did_document(did, public_jwk)

    async def resolve(self, did: str) -> dict:
        if did not in self.documents:
            raise DidResolutionError(f"{did} is not published")
        return self.documents[did]


@pytest.fixture
def resolver(client):
    """Install a stub DID resolver into the app under test, and hand it back."""
    stub = StubResolver()
    client._transport.app.dependency_overrides[get_did_resolver] = lambda: stub
    return stub


@pytest_asyncio.fixture(scope="function")
async def client(engine, tmp_path):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    test_settings = Settings(
        database_url=TEST_DATABASE_URL,
        oidc_issuer_url=None,
    )

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings_dep] = lambda: test_settings

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Registering a participant, after `D-51` ───────────────────────
#
# `POST /admin/participants` no longer creates a DID: the anchor does not invent
# a participant's identity, it records one the participant proved. So a test that
# needs a participant to exist has to say **which side it is standing on**, and
# the two are genuinely different rows:
#
#   as the anchor sees it        public key only — it can verify, never sign
#   as the participant holds it  private key too — it is its own STS
#
# Before the split those were one thing, which is exactly the conflation the
# split removes. Passing a test by creating the wrong one would put the old
# defect back inside the fixture.


async def register_holder(db, did: str, *, roles=None, scopes=None, secret="s3cret"):
    """A participant **on its own instance**: it holds the private key.

    What `ir-cli participant init` produces. Use this for anything exercising the
    STS or a presentation query — both need to sign.
    """
    from identity_registry.config import get_settings
    from identity_registry.db.models import Did as DidRow
    from identity_registry.db.models import Key, Participant
    from identity_registry.services.crypto import (
        encrypt_private_jwk,
        generate_key_pair,
        hash_sts_secret,
    )

    kp = generate_key_pair(did)
    key = Key(
        owner_did=did,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key),
        public_jwk=kp.public_jwk,
    )
    db.add(key)
    await db.flush()
    db.add(DidRow(did=did, did_type="participant", key_id=key.id))
    db.add(
        Participant(
            did=did,
            roles=list(roles or ["provider"]),
            allowed_scopes=list(scopes or ["dataspaces.query"]),
            sts_client_secret=hash_sts_secret(secret),
        )
    )
    await db.commit()
    return key


async def register_did(db, did: str):
    """Just the DID and its **public** key — no `Participant` row.

    What the anchor holds for a DID that has proved control of a key but has not
    (yet) been registered as a participant. Kept apart from `register_enrolled`
    because `POST /admin/participants` legitimately refuses a DID that already
    has a participant row, so a fixture that seeded both would make that route
    untestable.
    """
    from identity_registry.db.models import Did as DidRow
    from identity_registry.db.models import Key
    from identity_registry.services.crypto import generate_key_pair

    kp = generate_key_pair(did)
    key = Key(owner_did=did, kid=kp.kid, private_jwk=None, public_jwk=kp.public_jwk)
    db.add(key)
    await db.flush()
    db.add(DidRow(did=did, did_type="participant", key_id=key.id))
    await db.commit()
    return key


async def register_enrolled(db, did: str, *, roles=None, scopes=None):
    """A participant **as the trust anchor records it**: public key only.

    What enrolment produces. `sts_client_secret` is `None` deliberately — the
    anchor is not this participant's STS and must not be able to act as it.
    """
    from identity_registry.db.models import Did as DidRow
    from identity_registry.db.models import Key, Participant
    from identity_registry.services.crypto import generate_key_pair

    kp = generate_key_pair(did)
    key = Key(owner_did=did, kid=kp.kid, private_jwk=None, public_jwk=kp.public_jwk)
    db.add(key)
    await db.flush()
    db.add(DidRow(did=did, did_type="participant", key_id=key.id))
    db.add(
        Participant(
            did=did,
            roles=list(roles or ["consumer"]),
            allowed_scopes=list(scopes or ["dataspaces.query"]),
            sts_client_secret=None,
        )
    )
    await db.commit()
    return key


# ── Issuance: an anchor to sign with, a holder store to deliver to ─
#
# Both live here rather than in `test_enrolment.py` because two modules exercise
# the issuance path and a fixture imported across test modules is a fixture
# defined in the wrong place. Neither is `autouse` at this level: an anchor DID
# row in *every* test would change what the registry-listing tests see, and
# patching `httpx` globally would hide a real outbound call. The modules that
# want them always-on declare a one-line autouse shim.

#: Captured at import, before any fixture patches it. A test that patches
#: `httpx.AsyncClient` while the recorder already has would otherwise capture
#: *the recorder* as its "real" client and silently keep recording.
REAL_ASYNC_CLIENT = httpx.AsyncClient

ANCHOR_DID = "did:web:trust-anchor.dataspaces.localhost"


@pytest_asyncio.fixture
async def anchor_identity(db_session):
    """A bootstrapped trust anchor. Issuance is not possible without one.

    Every enrolment issues — the anchor signs a MembershipCredential and
    delivers it — so a registry with no signing key cannot complete the
    exchange, which `issue_for_participant` says in as many words rather than
    leaking an `OrgOnboardingError`.

    Deliberately *not* `anchor_bootstrap.ensure_identity`: this is the shape a
    registry bootstrapped before the `IssuerService` entry existed has — a key
    and a document publishing nothing — and `test_cip_conformance` asserts that
    re-running bootstrap repairs it.
    """
    from identity_registry.config import get_settings
    from identity_registry.db.models import Did, Key
    from identity_registry.services.crypto import encrypt_private_jwk, generate_key_pair

    kp = generate_key_pair(ANCHOR_DID)
    key = Key(
        owner_did=ANCHOR_DID,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key),
        public_jwk=kp.public_jwk,
    )
    db_session.add(key)
    await db_session.flush()
    db_session.add(
        Did(
            did=ANCHOR_DID,
            did_type="participant",
            display_name="Trust Anchor",
            key_id=key.id,
        )
    )
    await db_session.commit()
    return key


@pytest.fixture
def credential_store(monkeypatch):
    """A reachable holder credential store, recording what is delivered to it.

    Delivery is a real outbound `POST` to the endpoint the holder's DID document
    publishes. In a unit test nothing is listening there, so without this every
    enrolment would end `REJECTED` on a connection error — true, but it would
    make the delivery leg untestable and the enrolment leg unassertable.
    `test_a_delivery_failure_is_reported` removes it deliberately.
    """
    import json as _json

    from identity_registry.services import issuance

    delivered: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        delivered.append(
            {"url": str(request.url), "body": _json.loads(request.content or b"{}")}
        )
        return httpx.Response(201, json={"stored": []})

    transport = httpx.MockTransport(_handler)

    def _client(**kwargs):
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(issuance.httpx, "AsyncClient", _client)
    return delivered


#: The organisation a test's data subject belongs to. A person's DID lives in
#: their custodian's namespace since `DID-11` step 2, so a test issuing a member
#: credential has to say who holds it — there is no anchor-namespace fallback.
CUSTODIAN_DID = "did:web:rec.dataspaces.localhost"


async def register_custodian(db, did: str = CUSTODIAN_DID, *, credential_service=True):
    """A participant the anchor can deliver a person's credential to.

    Its `CredentialService` entry is what `deliver_to_custodian` reads — the one
    the participant published in its own DID document and proved control of at
    enrolment. Pass `credential_service=False` for the organisation that
    publishes none, which must be a refusal rather than a silent no-op.
    """
    from identity_registry.db.models import Did as DidRow
    from identity_registry.db.models import Key
    from identity_registry.services.crypto import generate_key_pair

    kp = generate_key_pair(did)
    key = Key(owner_did=did, kid=kp.kid, private_jwk=None, public_jwk=kp.public_jwk)
    db.add(key)
    await db.flush()
    db.add(
        DidRow(
            did=did,
            did_type="participant",
            key_id=key.id,
            service_endpoints=(
                [
                    {
                        "type": "CredentialService",
                        "serviceEndpoint": f"http://rec.dataspaces.localhost/credentials/{did}",
                    }
                ]
                if credential_service
                else []
            ),
        )
    )
    await db.commit()
    return did
