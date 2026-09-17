"""The organisation acting as itself on `/consumer/*` — and where it may not act.

Plan `the-management-api-is-v3-behind-one-key`, decisions 1-2 and the D-20
amendment (2026-09-17): an organisation's own client may negotiate and transfer
through ds's consumer routes, **bound to this connector's participant** and
holding **EDC's scope for the call ds makes** — and it never reads a person's
consents, and it gets no blanket service pass on provider writes.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.config import get_settings
from connector.db.engine import Base
from connector.db.models import ConsumerAccessRequestORM, ConsumerTransferORM
from connector.dependencies import get_consumer_service, get_db
from connector.main import create_app
from tests import make_headers, make_org_headers, make_vc_headers

CONSUMER_DID = "did:web:third-party.dataspaces.localhost"
SUBJECT_DID = f"{CONSUMER_DID}:users:consumer-user"
PROVIDER_DID = "did:web:rec.dataspaces.localhost"
ADDRESS = "http://provider.test/protocol/2025-1"
ASSET = "datasets.gold.test"


class _Prov:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        async def record(**kwargs):
            self.calls.append((name, kwargs))

        return record


class _Edc:
    async def get_transfer(self, _tid):
        return {"state": "STARTED"}

    async def get_negotiation(self, nid):
        return {"@id": nid, "state": "REQUESTED"}

    async def terminate_transfer(self, _tid, _reason=None):
        return None

    async def list_transfers(self):
        return [{"@id": "tp-1", "state": "STARTED"}]


class _Svc:
    def __init__(self) -> None:
        self._prov = _Prov()
        self._edc = _Edc()
        self.negotiated: list[dict] = []

    async def request_catalog(self, address, counter_party_id=None):
        return {"dataset": []}

    async def negotiate(self, **kwargs):
        self.negotiated.append(kwargs)
        return "neg-1"

    async def transfer(self, **kwargs):
        return "tp-1"

    async def get_edrs(self, ids):
        return {}


@pytest_asyncio.fixture
async def consumer(monkeypatch):
    """A consumer-role connector whose participant is the third party."""
    monkeypatch.setenv("CONNECTOR_ROLE", "consumer")
    monkeypatch.setenv("CONNECTOR_PARTICIPANT_DID", CONSUMER_DID)
    monkeypatch.setenv("CONNECTOR_CONSUMER_PARTICIPANT_DID", CONSUMER_DID)
    get_settings.cache_clear()
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    svc = _Svc()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_consumer_service] = lambda: svc
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, svc, factory
    await eng.dispose()
    get_settings.cache_clear()


NEGOTIATE = {
    "counter_party_address": ADDRESS,
    "offer_id": "offer-1",
    "asset_id": ASSET,
    "assigner": PROVIDER_DID,
}
TRANSFER = {
    "contract_agreement_id": "ag-1",
    "counter_party_address": ADDRESS,
    "asset_id": ASSET,
    "connector_id": PROVIDER_DID,
}


def _org(**kw) -> dict:
    return make_org_headers(context=kw.pop("context", CONSUMER_DID), **kw)


# ── It may negotiate and transfer, as itself ────────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_the_organisation_negotiates_under_its_own_ledger_key(consumer):
    client, svc, factory = consumer
    r = await client.post("/consumer/negotiate", json=NEGOTIATE, headers=_org())
    assert r.status_code == 200, r.text
    async with factory() as session:
        row = (await session.execute(select(ConsumerAccessRequestORM))).scalar_one()
    assert row.subject_id == f"org:{CONSUMER_DID}"


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_the_organisation_s_act_is_attributed_to_its_client(consumer):
    """DSSC-XCT-09: no person is named, and the client and the organisation are."""
    client, svc, _ = consumer
    await client.post("/consumer/negotiate", json=NEGOTIATE, headers=_org())
    calls = dict(svc._prov.calls)
    requested = calls["access_requested"]
    assert requested["user_id"] is None
    assert requested["acted_by"]["subject"] == CONSUMER_DID
    assert requested["acted_by"]["on_behalf_of"] == CONSUMER_DID
    assert requested["acted_by"]["client_id"] == "svc-ds-connector-example-org"
    assert requested["acted_by"]["is_service"] is True
    assert calls["negotiation_started"]["acted_by"] == requested["acted_by"]


@pytest.mark.asyncio
async def test_the_organisation_transfers_and_sees_only_its_own(consumer):
    client, _, factory = consumer
    r = await client.post("/consumer/transfer", json=TRANSFER, headers=_org())
    assert r.status_code == 200, r.text
    async with factory() as session:
        row = (await session.execute(select(ConsumerTransferORM))).scalar_one()
    assert row.subject_id == f"org:{CONSUMER_DID}"

    listed = await client.get("/consumer/transfers", headers=_org())
    assert [t["transfer_id"] for t in listed.json()] == ["tp-1"]
    # A person sees none of the organisation's transfers.
    person = await client.get(
        "/consumer/transfers",
        headers=make_vc_headers(
            SUBJECT_DID, role="ConsumerUser", linked_participant=CONSUMER_DID
        ),
    )
    assert person.status_code == 200
    assert person.json() == []


@pytest.mark.asyncio
async def test_a_person_s_negotiation_is_not_the_organisation_s(consumer):
    client, _, _ = consumer
    person = make_vc_headers(
        SUBJECT_DID, role="ConsumerUser", linked_participant=CONSUMER_DID
    )
    assert (
        await client.post("/consumer/negotiate", json=NEGOTIATE, headers=person)
    ).status_code == 200
    r = await client.get("/consumer/negotiations/neg-1", headers=_org())
    assert r.status_code == 404


# ── …bound to this participant, with EDC's scope ────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.asyncio
async def test_another_participant_s_organisation_token_is_refused(consumer):
    client, svc, _ = consumer
    r = await client.post(
        "/consumer/negotiate",
        json=NEGOTIATE,
        headers=_org(context="did:web:someone-else.example.org"),
    )
    assert r.status_code == 403
    assert "own participant" in r.json()["detail"]
    assert svc.negotiated == []


@pytest.mark.parametrize(
    "path,body,scopes,missing",
    [
        (
            "/consumer/negotiate",
            NEGOTIATE,
            ("management-api:negotiations:read",),
            "negotiations:write",
        ),
        (
            "/consumer/transfer",
            TRANSFER,
            ("management-api:negotiations:write",),
            "transfers:write",
        ),
        (
            "/consumer/catalog",
            {"counter_party_address": ADDRESS},
            ("management-api:transfers:write",),
            "catalog:read",
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_missing_edc_scope_is_refused(consumer, path, body, scopes, missing):
    client, _, _ = consumer
    r = await client.post(path, json=body, headers=_org(scopes=scopes))
    assert r.status_code == 403
    assert missing in r.json()["detail"]


@pytest.mark.asyncio
async def test_read_routes_accept_the_write_scope(consumer):
    """EDC's grammar: `write` satisfies `read`."""
    client, _, _ = consumer
    r = await client.get(
        "/consumer/requests",
        headers=_org(scopes=("management-api:negotiations:write",)),
    )
    assert r.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        # A service that is not an organisation, even holding every EDC scope.
        make_headers(scope="management-api:negotiations:write connector.consumer.read"),
        # A person's bearer token is not a ConsumerUser credential.
        {"Authorization": "Bearer not-a-jwt"},
    ],
)
@pytest.mark.asyncio
async def test_nothing_else_negotiates(consumer, headers):
    client, svc, _ = consumer
    r = await client.post("/consumer/negotiate", json=NEGOTIATE, headers=headers)
    assert r.status_code in (401, 403)
    assert svc.negotiated == []


@pytest.mark.asyncio
async def test_no_credential_is_a_401(consumer):
    client, _, _ = consumer
    assert (await client.post("/consumer/negotiate", json=NEGOTIATE)).status_code == 401


@pytest.mark.asyncio
async def test_the_organisation_reads_a_catalogue_with_the_edc_scope(consumer):
    client, svc, _ = consumer
    r = await client.post(
        "/consumer/catalog", json={"counter_party_address": ADDRESS}, headers=_org()
    )
    assert r.status_code == 200
    ((name, viewed),) = svc._prov.calls
    assert name == "catalog_viewed"
    assert viewed["user_id"] is None


@pytest.mark.asyncio
async def test_a_person_keeps_the_credential_path(consumer):
    client, svc, factory = consumer
    person = make_vc_headers(
        SUBJECT_DID, role="ConsumerUser", linked_participant=CONSUMER_DID
    )
    r = await client.post("/consumer/negotiate", json=NEGOTIATE, headers=person)
    assert r.status_code == 200
    async with factory() as session:
        row = (await session.execute(select(ConsumerAccessRequestORM))).scalar_one()
    assert row.subject_id == SUBJECT_DID
    requested = dict(svc._prov.calls)["access_requested"]
    assert requested["user_id"] == SUBJECT_DID
    assert requested["acted_by"] is None


# ── …and never a person's consents (D-20) ───────────────────────────────────


@pytest.mark.rule("D-20")
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/consent/my", None),
        ("GET", "/consent/my/shares", None),
        ("POST", "/consent/my/shares", {"offer_id": "x", "enabled": True}),
        (
            "GET",
            "/consent/status?subject_id=did:web:x&consumer_id=did:web:y"
            "&dataset_id=datasets.silver.meters",
            None,
        ),
    ],
)
@pytest.mark.asyncio
async def test_an_organisation_token_reads_no_person_s_consents(
    client, method, path, body
):
    """The provider's subject-facing surface authenticates the subject's
    credential. An organisation token — even this participant's own — is not
    one, whatever EDC scopes it holds. A complete request, so the refusal is
    about the credential and not the body."""
    r = await client.request(method, path, headers=make_org_headers(), json=body)
    assert r.status_code == 401, r.text
    assert "Verifiable Credential" in r.json()["detail"]
