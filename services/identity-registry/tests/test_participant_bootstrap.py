"""The participant half of enrolment — and the two halves against each other.

Most of this file is one test: **two instances, two databases, one signature.**
A participant generates a keypair its own database holds, publishes a DID
document from its own `/dids` route, and enrols with an anchor that has never
seen the private key and verifies the request by fetching that document.

That is the claim `D-47` makes, and it is not provable by testing either side
alone — which is why the anchor's own suite (`test_enrolment.py`) fabricates a
client, and this one runs the real thing.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from conftest import TEST_DATABASE_URL, StubResolver, make_admin_headers
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from identity_registry.config import Settings, get_settings
from identity_registry.db.engine import Base
from identity_registry.db.models import Did, Key, Owner, Participant
from identity_registry.dependencies import get_db, get_settings_dep
from identity_registry.main import create_app
from identity_registry.services import participant_bootstrap as boot

HEADERS = make_admin_headers()

REC_DID = "did:web:rec.dataspaces.localhost"
REC_URL = "http://rec.dataspaces.localhost"
DSP = "http://172.17.0.1:19194/protocol/2025-1"


def participant_settings(**overrides) -> Settings:
    base = {
        "database_url": TEST_DATABASE_URL,
        "oidc_issuer_url": None,
        "role": "participant",
        "participant_did": REC_DID,
        "identity_registry_public_url": REC_URL,
        "participant_dsp_address": DSP,
        # A participant's own key, distinct from the anchor's. Sharing one is
        # what `D-47` forbids, so the fixture must not model it.
        "encryption_key": "participant-instance-key-not-the-anchors",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest_asyncio.fixture
async def participant_db():
    """A second database — the participant's. Never the anchor's."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def participant_app(participant_db, monkeypatch):
    """A running `participant`-role instance, serving its own DID document."""
    monkeypatch.setenv("IDENTITY_REGISTRY_ROLE", "participant")
    monkeypatch.setenv("IDENTITY_REGISTRY_PARTICIPANT_DID", REC_DID)
    get_settings.cache_clear()

    settings = participant_settings()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: participant_db
    app.dependency_overrides[get_settings_dep] = lambda: settings

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=REC_URL
    ) as ac:
        yield ac
    get_settings.cache_clear()


# ── Holding an identity ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_instance_generates_and_holds_its_own_key(participant_db):
    settings = participant_settings()
    identity = await boot.ensure_identity(participant_db, settings)
    await participant_db.commit()

    assert identity.created
    key = (
        await participant_db.execute(select(Key).where(Key.owner_did == REC_DID))
    ).scalar_one()
    # The half that never leaves.
    assert key.private_jwk is not None
    assert key.public_jwk["kid"] == identity.kid


@pytest.mark.asyncio
async def test_it_publishes_its_own_credential_service_and_dsp_endpoint(
    participant_db,
):
    settings = participant_settings()
    identity = await boot.ensure_identity(participant_db, settings)

    published = {e["type"]: e["serviceEndpoint"] for e in identity.service_endpoints}
    assert published["DSPEndpoint"] == DSP
    # Its own host — not the anchor's. This is the value a counterparty follows.
    assert published["CredentialService"] == f"{REC_URL}/credentials/{REC_DID}"


@pytest.mark.asyncio
async def test_ensure_identity_is_idempotent_and_never_rotates(participant_db):
    """A bootstrap that rotated on restart would silently invalidate credentials."""
    settings = participant_settings()
    first = await boot.ensure_identity(participant_db, settings)
    await participant_db.commit()
    second = await boot.ensure_identity(participant_db, settings)
    await participant_db.commit()

    assert second.created is False
    assert second.kid == first.kid
    keys = (
        await participant_db.execute(select(Key).where(Key.owner_did == REC_DID))
    ).scalars().all()
    assert len(keys) == 1


@pytest.mark.asyncio
async def test_re_running_refreshes_what_is_published(participant_db):
    await boot.ensure_identity(participant_db, participant_settings())
    await participant_db.commit()

    moved = participant_settings(
        participant_dsp_address="http://172.17.0.1:19999/protocol/2025-1"
    )
    await boot.ensure_identity(participant_db, moved)
    await participant_db.commit()

    row = (
        await participant_db.execute(select(Did).where(Did.did == REC_DID))
    ).scalar_one()
    published = {e["type"]: e["serviceEndpoint"] for e in row.service_endpoints}
    assert published["DSPEndpoint"].endswith(":19999/protocol/2025-1")


@pytest.mark.asyncio
async def test_no_did_configured_is_a_refusal(participant_db):
    settings = participant_settings(participant_did=None)
    with pytest.raises(boot.ParticipantBootstrapError) as excinfo:
        await boot.ensure_identity(participant_db, settings)
    assert "PARTICIPANT_DID" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_public_only_key_under_our_own_did_is_a_refusal(participant_db):
    """Two instances sharing one database — the thing the split exists to stop.

    Generating a second key beside the first would leave two active keys for one
    DID and a document that publishes whichever was found first.
    """
    from identity_registry.services.crypto import generate_key_pair

    kp = generate_key_pair(REC_DID)
    participant_db.add(
        Key(owner_did=REC_DID, kid=kp.kid, private_jwk=None, public_jwk=kp.public_jwk)
    )
    await participant_db.commit()

    with pytest.raises(boot.ParticipantBootstrapError) as excinfo:
        await boot.ensure_identity(participant_db, participant_settings())
    assert "sharing a database" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_participant_instance_serves_its_own_did_document(
    participant_app, participant_db
):
    await boot.ensure_identity(participant_db, participant_settings())
    await participant_db.commit()

    r = await participant_app.get(f"/dids/{REC_DID}/did.json")
    assert r.status_code == 200
    document = r.json()
    assert document["id"] == REC_DID
    # The document publishes a public key and nothing else.
    jwk = document["verificationMethod"][0]["publicKeyJwk"]
    assert "d" not in jwk
    services = {s["type"]: s["serviceEndpoint"] for s in document["service"]}
    assert services["CredentialService"] == f"{REC_URL}/credentials/{REC_DID}"


@pytest.mark.asyncio
async def test_a_participant_instance_refuses_to_start_with_no_did(monkeypatch):
    """Otherwise it reports healthy and 404s everything."""
    from identity_registry.roles import RoleConfigurationError

    monkeypatch.setenv("IDENTITY_REGISTRY_ROLE", "participant")
    monkeypatch.delenv("IDENTITY_REGISTRY_PARTICIPANT_DID", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RoleConfigurationError) as excinfo:
        create_app()
    assert "PARTICIPANT_DID" in str(excinfo.value)
    get_settings.cache_clear()


# ── The two halves, against each other ────────────────────────────


@pytest.mark.asyncio
async def test_a_participant_enrols_with_an_anchor_that_never_sees_its_key(
    client, db_session, resolver, participant_app, participant_db, monkeypatch
):
    """The end-to-end claim of `D-47`, with both sides real.

    The participant generates a key in *its* database and serves its own DID
    document; the anchor resolves that document over what it believes is the
    network, verifies the signature against the key published there, and records
    the public half in *its* database. Two databases, one signature, and the
    private key never crosses.
    """
    # 1. The organisation exists and has been admitted.
    db_session.add(
        Owner(
            id="rec",
            type="schema:Organization",
            name="Riverside Energy Community",
            status="verified",
            verified_by="ops@example.test",
        )
    )
    await db_session.commit()
    issued = await client.post(
        "/admin/onboarding/enrolments", json={"owner_alias": "rec"}, headers=HEADERS
    )
    code = issued.json()["code"]

    # 2. The participant generates its own key and publishes its document.
    settings = participant_settings()
    await boot.ensure_identity(participant_db, settings)
    await participant_db.commit()

    published = (await participant_app.get(f"/dids/{REC_DID}/did.json")).json()
    # What the anchor will fetch is exactly what the participant serves.
    resolver.documents[REC_DID] = published

    # 3. Route the participant's outbound HTTP into the anchor's ASGI app —
    #    real httpx, real request, no network.
    anchor_app = client._transport.app
    real_client = httpx.AsyncClient

    def _to_anchor(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=ASGITransport(app=anchor_app), **kwargs)

    monkeypatch.setattr(boot.httpx, "AsyncClient", _to_anchor)

    result = await boot.enrol(participant_db, settings, code=code)
    await participant_db.commit()

    assert result.status == "RECEIVED"
    assert result.issuer_pid
    assert result.location == f"/issuer/requests/{result.issuer_pid}"

    # 4. The anchor knows the participant, and holds no key it could sign with.
    anchor_key = (
        await db_session.execute(select(Key).where(Key.owner_did == REC_DID))
    ).scalar_one()
    assert anchor_key.private_jwk is None
    assert anchor_key.public_jwk == published["verificationMethod"][0]["publicKeyJwk"]

    participant_row = (
        await db_session.execute(select(Participant).where(Participant.did == REC_DID))
    ).scalar_one()
    assert participant_row.dsp_address == DSP
    assert participant_row.sts_client_secret is None

    # 5. And the participant still holds the private half nobody else has.
    own_key = (
        await participant_db.execute(select(Key).where(Key.owner_did == REC_DID))
    ).scalar_one()
    assert own_key.private_jwk is not None


@pytest.mark.asyncio
async def test_enrolling_before_generating_a_key_is_a_refusal(participant_db):
    with pytest.raises(boot.ParticipantBootstrapError) as excinfo:
        await boot.enrol(participant_db, participant_settings(), code="anything")
    assert "No private key" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_refusal_from_the_anchor_names_both_things_to_check(
    participant_db, monkeypatch
):
    """The message an operator will actually meet in `DID-05`.

    The anchor deliberately does not say which half failed, so this side has to
    name the two candidates: a spent code, or a DID the anchor cannot resolve.
    """
    settings = participant_settings()
    await boot.ensure_identity(participant_db, settings)
    await participant_db.commit()

    # Capture the real class first: `boot.httpx` *is* the httpx module, so
    # patching it patches it everywhere — including inside the replacement.
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"detail": "Enrolment refused"})
    )

    def _refusing(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(boot.httpx, "AsyncClient", _refusing)

    with pytest.raises(boot.ParticipantBootstrapError) as excinfo:
        await boot.enrol(participant_db, settings, code="stale")
    message = str(excinfo.value)
    assert "401" in message
    assert "enrolment code" in message
    assert "resolves from the anchor" in message


@pytest.mark.asyncio
async def test_an_unreachable_issuer_says_which_url(participant_db, monkeypatch):
    settings = participant_settings()
    await boot.ensure_identity(participant_db, settings)
    await participant_db.commit()

    real_client = httpx.AsyncClient

    def _raise(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_raise)

    def _broken(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(boot.httpx, "AsyncClient", _broken)

    with pytest.raises(boot.ParticipantBootstrapError) as excinfo:
        await boot.enrol(participant_db, settings, code="x")
    assert settings.issuer_base_url in str(excinfo.value)


# ── Where the anchor is ───────────────────────────────────────────


def test_the_issuer_url_defaults_to_the_anchors_did_host():
    settings = participant_settings(trust_anchor_url=None, did_web_use_https=False)
    assert settings.issuer_base_url == "http://trust-anchor.dataspaces.localhost"


def test_the_issuer_url_follows_the_did_web_scheme():
    """A production instance must not enrol over plain HTTP by omission."""
    settings = participant_settings(trust_anchor_url=None, did_web_use_https=True)
    assert settings.issuer_base_url.startswith("https://")


def test_an_explicit_issuer_url_wins():
    settings = participant_settings(trust_anchor_url="http://172.17.0.1:30005/")
    assert settings.issuer_base_url == "http://172.17.0.1:30005"


def test_the_stub_resolver_is_not_what_the_anchor_uses_in_production():
    """Guard on the fixture, not the code: `StubResolver` must stay test-only."""
    import inspect

    from identity_registry.services import did_resolver

    assert "StubResolver" not in inspect.getsource(did_resolver)
    assert issubclass(StubResolver, object)
