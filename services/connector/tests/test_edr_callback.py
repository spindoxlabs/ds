"""The EDR reaches the connector on the transfer's own callback.

EDC 0.18.0's v5 management API has no EDR endpoint. A consumer transfer names a
callback address; EDC posts ``TransferProcessStarted`` there with the EDR, from
its vault it takes the header value, and ``POST /webhooks/edc-callback`` keeps
the EDR. What each test pins was measured against a running 0.18.0 runtime.
"""

from __future__ import annotations

import asyncio

import pytest
from ds_edc import CallbackAddress
from ds_edc.schemas import EdrResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.config import Settings, get_settings
from connector.db.models import EdrEntryORM
from connector.services.consumer_service import (
    EDC_CALLBACK_AUTH_HEADER,
    ConsumerService,
    NoEdrCallback,
    edr_callback_address,
)
from connector.services.edr_store import EdrNotReceived, EdrStore

NS = "https://w3id.org/edc/v0.0.1/ns/"


def _started(context: str | None = None, **payload) -> dict:
    body = {
        "id": "evt-1",
        "at": 1789645894183,
        "type": "TransferProcessStarted",
        "payload": {
            "transferProcessId": "tp-1",
            "contractId": "ag-1",
            "assetId": "datasets.gold.test",
            "type": "CONSUMER",
            "participantContextId": context or get_settings().participant_context_id,
            "dataAddress": {
                "properties": {
                    f"{NS}type": "https://w3id.org/idsa/v4.1/HTTP",
                    f"{NS}endpoint": "http://dp/query",
                    f"{NS}authType": "bearer",
                    f"{NS}authorization": "eyJ.token",
                }
            },
        },
    }
    body["payload"].update(payload)
    return body


def _key() -> dict:
    return {EDC_CALLBACK_AUTH_HEADER: get_settings().edc_callback_secret}


@pytest.fixture
def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


# -- The route -----------------------------------------------------------------


async def test_a_started_transfer_s_edr_is_stored(client, factory):
    r = await client.post("/webhooks/edc-callback", json=_started(), headers=_key())
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "stored", "transfer_id": "tp-1"}

    async with factory() as session:
        row = await session.get(EdrEntryORM, "tp-1")
    assert row is not None
    assert (row.endpoint, row.authorization, row.auth_type) == (
        "http://dp/query",
        "eyJ.token",
        "bearer",
    )
    assert row.agreement_id == "ag-1"
    assert row.asset_id == "datasets.gold.test"
    # Kept as delivered, for a data plane that is not HTTP-pull.
    assert row.data_address["properties"][f"{NS}endpoint"] == "http://dp/query"


async def test_a_second_event_refreshes_the_edr(client, factory):
    await client.post("/webhooks/edc-callback", json=_started(), headers=_key())
    refreshed = _started()
    refreshed["payload"]["dataAddress"]["properties"][f"{NS}authorization"] = "new"
    r = await client.post("/webhooks/edc-callback", json=refreshed, headers=_key())
    assert r.status_code == 200
    async with factory() as session:
        assert (await session.get(EdrEntryORM, "tp-1")).authorization == "new"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {EDC_CALLBACK_AUTH_HEADER: "wrong"},
        {EDC_CALLBACK_AUTH_HEADER: ""},
        # A realm token is not the callback's credential.
        {"Authorization": "Bearer anything"},
    ],
)
async def test_the_callback_key_is_required(client, factory, headers):
    r = await client.post("/webhooks/edc-callback", json=_started(), headers=headers)
    assert r.status_code == 401
    async with factory() as session:
        assert await session.get(EdrEntryORM, "tp-1") is None


async def test_an_event_for_another_participant_context_is_refused(client, factory):
    body = _started(context="did:web:someone-else.example.org")
    r = await client.post("/webhooks/edc-callback", json=body, headers=_key())
    assert r.status_code == 403
    async with factory() as session:
        assert await session.get(EdrEntryORM, "tp-1") is None


async def test_a_started_event_without_an_edr_is_refused_not_stored(client, factory):
    body = _started(dataAddress={"properties": {f"{NS}endpoint": "http://dp"}})
    r = await client.post("/webhooks/edc-callback", json=body, headers=_key())
    assert r.status_code == 422
    async with factory() as session:
        assert await session.get(EdrEntryORM, "tp-1") is None


async def test_other_events_are_acknowledged_and_dropped(client, factory):
    body = _started()
    body["type"] = "TransferProcessCompleted"
    r = await client.post("/webhooks/edc-callback", json=body, headers=_key())
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
    async with factory() as session:
        assert await session.get(EdrEntryORM, "tp-1") is None


# -- The store -----------------------------------------------------------------


async def test_the_store_waits_for_an_edr_that_is_on_its_way(factory):
    store = EdrStore(factory, wait_timeout=2, poll_interval=0.05)

    async def arrive():
        await asyncio.sleep(0.2)
        async with factory() as session:
            session.add(
                EdrEntryORM(
                    transfer_id="tp-2",
                    endpoint="http://dp",
                    authorization="tok",
                    auth_type="bearer",
                    data_address={},
                )
            )
            await session.commit()

    task = asyncio.create_task(arrive())
    edr = await store.wait_for("tp-2")
    await task
    assert edr == EdrResponse(endpoint="http://dp", authorization="tok")


async def test_a_missing_edr_is_a_timeout_that_says_why(factory):
    store = EdrStore(factory, wait_timeout=0.1, poll_interval=0.05)
    with pytest.raises(EdrNotReceived, match="CONNECTOR_EDC_CALLBACK_URL"):
        await store.wait_for("tp-none")


async def test_many_edrs_are_read_at_once(factory):
    async with factory() as session:
        for tid in ("a", "b"):
            session.add(
                EdrEntryORM(
                    transfer_id=tid,
                    endpoint=f"http://{tid}",
                    authorization="t",
                    auth_type="bearer",
                    data_address={},
                )
            )
        await session.commit()
    store = EdrStore(factory)
    found = await store.get_many(["a", "b", "c"])
    assert set(found) == {"a", "b"}
    assert await store.get_many([]) == {}


# -- The transfer names the callback -------------------------------------------


def test_the_callback_names_the_header_and_the_vault_alias():
    settings = Settings(
        role="consumer",
        edc_callback_url="http://connector:31001/webhooks/edc-callback",
        edc_callback_auth_code_id="alias-x",
    )
    cb = edr_callback_address(settings)
    assert cb == CallbackAddress(
        uri="http://connector:31001/webhooks/edc-callback",
        events=["transfer.process.started"],
        auth_key=EDC_CALLBACK_AUTH_HEADER,
        auth_code_id="alias-x",
    )


def test_no_callback_url_means_no_callback():
    assert edr_callback_address(Settings(role="consumer")) is None


class _Edc:
    def __init__(self):
        self.requests = []

    async def start_transfer(self, req):
        self.requests.append(req)
        return "tp-9"


async def test_a_transfer_carries_the_callback():
    edc = _Edc()
    cb = CallbackAddress(uri="http://c/cb", events=["transfer.process.started"])
    svc = ConsumerService(
        consumer_edc=edc, registry=None, prov=None, edrs=object(), callback=cb
    )
    assert await svc.transfer("ag", "http://p", "a", "did:web:p") == "tp-9"
    assert edc.requests[0].callback_addresses == [cb]


async def test_a_transfer_without_a_callback_is_refused_before_it_exists():
    """v5 cannot be asked for the EDR afterwards, so such a transfer is useless."""
    edc = _Edc()
    svc = ConsumerService(consumer_edc=edc, registry=None, prov=None)
    with pytest.raises(NoEdrCallback):
        await svc.transfer("ag", "http://p", "a", "did:web:p")
    assert edc.requests == []
