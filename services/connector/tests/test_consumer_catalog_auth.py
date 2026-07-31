"""`POST /consumer/catalog` — the guard, and what it attributes the view to.

The route had no guard of any kind while every sibling `/consumer/*` route
required a `ConsumerUser` VC-JWT (defect **P0-1**, rulebook `C-19` /
`DSSC-PUB-27`: a discovering consumer must be a registered participant). It also
attributed `CatalogViewed` to a caller-supplied `X-Subject-Id` header, which
rulebook `D-16` forbids — the recorded identity must be a verified one.

Two caller classes are legitimate and they authenticate differently, so both
paths are asserted here along with what each records:

* a **person** acting for a consumer organisation (VC-JWT) — what `ds-e2e`'s
  smoke flow presents;
* a **service** driving the consumer side (`connector.consumer.read`) — the
  federated catalogue's crawler, which previously sent nothing at all.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.config import get_settings
from connector.db.engine import Base
from connector.dependencies import get_consumer_service, get_db
from connector.main import create_app
from tests import make_headers, make_user_headers, make_vc_headers

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

CONSUMER_DID = "did:web:consumer.dataspaces.localhost"
SUBJECT_DID = "did:web:users.dataspaces.localhost:consumer-user"


class _RecordingProv:
    """Captures `catalog_viewed` kwargs so attribution can be asserted."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def catalog_viewed(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _FakeConsumerService:
    def __init__(self) -> None:
        self._prov = _RecordingProv()

    async def request_catalog(self, counter_party_address, counter_party_id=None):
        return {"dataset": [{"@id": "urn:dataset:1"}]}


@pytest_asyncio.fixture(scope="function")
async def consumer_app(monkeypatch):
    """A consumer-role app — `/consumer/*` mounts in that role only.

    The settings object is process-cached, so the role has to be set and the
    cache dropped before `create_app` reads it, and dropped again afterwards so
    the provider-role suite is unaffected.
    """
    monkeypatch.setenv("CONNECTOR_ROLE", "consumer")
    monkeypatch.setenv("CONNECTOR_CONSUMER_PARTICIPANT_DID", CONSUMER_DID)
    get_settings.cache_clear()

    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    svc = _FakeConsumerService()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_consumer_service] = lambda: svc

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, svc

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()
    get_settings.cache_clear()


BODY = {"counter_party_address": "http://provider.test/protocol/2025-1"}


@pytest.mark.asyncio
async def test_catalog_without_any_credential_is_refused(consumer_app):
    """The defect itself: this returned 200 and a full catalogue."""
    client, _ = consumer_app
    r = await client.post("/consumer/catalog", json=BODY)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_catalog_rejects_a_bare_subject_header(consumer_app):
    """A header alone is not an identity — it is what `D-16` rules out.

    Sending `X-Subject-Id` with no credential used to be enough to have the
    catalogue view attributed to that subject.
    """
    client, svc = consumer_app
    r = await client.post(
        "/consumer/catalog", json=BODY, headers={"X-Subject-Id": SUBJECT_DID}
    )
    assert r.status_code == 401
    assert svc._prov.calls == []


@pytest.mark.asyncio
async def test_catalog_refuses_a_service_token_without_the_scope(consumer_app):
    client, _ = consumer_app
    r = await client.post(
        "/consumer/catalog", json=BODY, headers=make_headers(scope="provenance.write")
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_catalog_refuses_a_user_holding_no_consumer_credential(consumer_app):
    """A group-authenticated human is not a consumer user.

    `ds-member` reaches the federated catalogue; driving a DSP catalogue request
    as the participant needs the credential, not the group.
    """
    client, _ = consumer_app
    r = await client.post(
        "/consumer/catalog", json=BODY, headers=make_user_headers(["ds-member"])
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_catalog_accepts_the_crawler_and_names_no_person(consumer_app):
    """The federated catalogue's path.

    A service fetches on the participant's behalf, so `user_id` stays `None`:
    recording the client id there would make an automated crawl indistinguishable
    from a person browsing.
    """
    client, svc = consumer_app
    r = await client.post(
        "/consumer/catalog",
        json=BODY,
        headers=make_headers(scope="connector.consumer.read"),
    )
    assert r.status_code == 200

    (event,) = svc._prov.calls
    assert event["user_id"] is None
    assert event["consumer_id"] == CONSUMER_DID


@pytest.mark.asyncio
async def test_catalog_accepts_a_consumer_user_and_attributes_to_them(consumer_app):
    client, svc = consumer_app
    r = await client.post(
        "/consumer/catalog",
        json=BODY,
        headers=make_vc_headers(
            subject_did=SUBJECT_DID,
            role="ConsumerUser",
            linked_participant=CONSUMER_DID,
        ),
    )
    assert r.status_code == 200

    (event,) = svc._prov.calls
    assert event["user_id"] == SUBJECT_DID
    # The idempotency key is derived from the verified actor, so one caller
    # cannot claim another's event id.
    assert SUBJECT_DID in event["event_id"]


@pytest.mark.asyncio
async def test_catalog_refuses_a_subject_credential(consumer_app):
    """VC roles are additive but not interchangeable — `DataSubject` is not it."""
    client, _ = consumer_app
    r = await client.post(
        "/consumer/catalog",
        json=BODY,
        headers=make_vc_headers(
            subject_did=SUBJECT_DID,
            role="DataSubject",
            linked_participant=CONSUMER_DID,
        ),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_catalog_refuses_a_credential_linked_to_another_participant(consumer_app):
    client, _ = consumer_app
    r = await client.post(
        "/consumer/catalog",
        json=BODY,
        headers=make_vc_headers(
            subject_did=SUBJECT_DID,
            role="ConsumerUser",
            linked_participant="did:web:someone-else.dataspaces.localhost",
        ),
    )
    assert r.status_code == 403
