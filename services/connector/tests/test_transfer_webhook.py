"""`POST /webhooks/transfer-process` — the transfer half of EDC's lifecycle.

The route existed with **no producer in any deployment**, which left a provider
emitting no `DataTransferCompleted` at all — one of the sixteen events rulebook
`L-1` makes mandatory for every participant. `TransferEventPublisher` in
`services/edc-extensions` is now that producer; these assert the receiving end.

Two things are pinned here that the route got wrong while it was unreachable:
the counterparties were a **hardcoded literal**, and *started* and *completed*
emitted the same event.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.dependencies import get_db, get_notifier
from connector.main import create_app
from connector.services.agreement_service import upsert_agreement
from tests import make_headers

WEBHOOK = make_headers(scope="connector.webhook")

AGREEMENT = "agr-transfer-1"
TRANSFER = "tp-9"
ASSET = "datasets.silver.meters"
CONSUMER = "did:web:consumer.dataspaces.localhost"
PROVIDER = "did:web:provider.dataspaces.localhost"


class FakeProv:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def transfer_started(self, **kwargs) -> None:
        self.calls.append(("transfer_started", kwargs))

    async def data_transfer_completed(self, **kwargs) -> None:
        self.calls.append(("data_transfer_completed", kwargs))

    def of(self, name: str) -> list[dict]:
        return [kw for n, kw in self.calls if n == name]


@pytest_asyncio.fixture
async def client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_notifier] = lambda: None
    fake = FakeProv()
    # The route reads `request.app.state.prov`, not a dependency.
    app.state.prov = fake

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, fake


@pytest_asyncio.fixture
async def agreement(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await upsert_agreement(
            session,
            agreement_id=AGREEMENT,
            asset_id=ASSET,
            consumer_id=CONSUMER,
            provider_id=PROVIDER,
            policy_snapshot={},
            agreed_at=datetime.now(UTC),
        )
        await session.commit()


async def _post(client, event_type: str, **payload):
    body = {
        "id": "evt-1",
        "type": event_type,
        "payload": {
            "transferProcessId": TRANSFER,
            "assetId": ASSET,
            "contractId": AGREEMENT,
            "role": "PROVIDER",
            **payload,
        },
    }
    return await client.post("/webhooks/transfer-process", json=body, headers=WEBHOOK)


# ── the event a provider emits nowhere else ──────────────────────────────────


@pytest.mark.asyncio
async def test_completed_emits_data_transfer_completed(client, agreement):
    ac, prov = client
    assert (await _post(ac, "TRANSFER_PROCESS_COMPLETED")).status_code == 200
    emitted = prov.of("data_transfer_completed")
    assert len(emitted) == 1
    assert emitted[0]["transfer_id"] == TRANSFER
    assert emitted[0]["agreement_id"] == AGREEMENT
    assert emitted[0]["data_product_id"] == ASSET


@pytest.mark.asyncio
async def test_started_and_completed_are_different_events(client, agreement):
    """A transfer that has started has moved no data yet.

    The route used to emit `DataTransferCompleted` for both, so a started
    transfer was recorded as a finished one.
    """
    ac, prov = client
    await _post(ac, "TRANSFER_PROCESS_STARTED")
    assert prov.of("transfer_started")
    assert not prov.of("data_transfer_completed")

    await _post(ac, "TRANSFER_PROCESS_COMPLETED")
    assert prov.of("data_transfer_completed")


@pytest.mark.asyncio
async def test_a_state_that_settles_nothing_emits_nothing(client, agreement):
    ac, prov = client
    assert (await _post(ac, "TRANSFER_PROCESS_REQUESTED")).status_code == 200
    assert prov.calls == []


# ── attribution ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_counterparties_come_from_the_agreement(client, agreement):
    """Not from a literal, and not from the event.

    `consumer_id="consumer"` was hardcoded, so every completed transfer named the
    same non-existent participant. The agreement is this connector's own record
    of who signed what; the event is the counterparty's account of itself.
    """
    ac, prov = client
    await _post(ac, "TRANSFER_PROCESS_COMPLETED")
    emitted = prov.of("data_transfer_completed")[0]
    assert emitted["consumer_id"] == CONSUMER
    assert emitted["provider_id"] == PROVIDER
    assert "consumer" != emitted["consumer_id"]


@pytest.mark.asyncio
async def test_an_event_naming_no_known_agreement_is_not_attributed(client):
    """No agreement on record means nobody to name.

    Emitting with `"unknown"` in the participant fields would put a fabricated
    actor into the provenance graph, which is worse than the gap it fills.
    """
    ac, prov = client
    r = await _post(ac, "TRANSFER_PROCESS_COMPLETED", contractId="agr-nobody-knows")
    assert r.status_code == 200
    assert prov.calls == []


@pytest.mark.asyncio
async def test_the_event_cannot_reassign_the_counterparties(client, agreement):
    """A payload claiming other participants changes nothing."""
    ac, prov = client
    await _post(
        ac,
        "TRANSFER_PROCESS_COMPLETED",
        consumerId="did:web:attacker.dataspaces.localhost",
        providerId="did:web:attacker.dataspaces.localhost",
    )
    emitted = prov.of("data_transfer_completed")[0]
    assert emitted["consumer_id"] == CONSUMER
    assert emitted["provider_id"] == PROVIDER


# ── the route is not open ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_it_requires_the_webhook_grant(client, agreement):
    ac, _ = client
    r = await ac.post(
        "/webhooks/transfer-process",
        json={"id": "evt-1", "type": "TRANSFER_PROCESS_COMPLETED", "payload": {}},
        headers=make_headers(scope="connector.provider.read"),
    )
    assert r.status_code == 403
