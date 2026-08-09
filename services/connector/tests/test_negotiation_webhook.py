"""`POST /webhooks/contract-negotiation` — trace correlation on the shared id.

This route had **no test in this suite** before, which is worth saying rather
than quietly fixing: it is the one place a provider learns an agreement exists,
and `dsp_agreement_id` — the value `EDCL-06` settled as the correlation key —
reaches this platform through it and nowhere else.

Scope is deliberately narrow. What is pinned here is the correlation, because
that is what this change adds; the record-keeping the handler also does is
covered by `test_transfer_webhook.py` through the agreement it reads back.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.dependencies import get_db, get_notifier
from connector.main import create_app
from tests import make_headers

WEBHOOK = make_headers(scope="connector.webhook")

NEGOTIATION = "neg-1"
LOCAL_AGREEMENT = "agr-local-1"
SHARED_AGREEMENT = "dsp-shared-1"
ASSET = "datasets.silver.meters"


@pytest_asyncio.fixture
async def client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_notifier] = lambda: None
    app.state.prov = None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def correlated(monkeypatch):
    """Capture at the call site — the ContextVar is per-task, so reading it from
    the test would return `None` whether or not the handler set it."""
    captured: list[str | None] = []
    from connector.api.v1 import webhooks as module

    monkeypatch.setattr(module, "correlate_agreement", captured.append)
    return captured


async def _post(client, event_type: str, **payload):
    body = {
        "id": "evt-1",
        "type": event_type,
        "payload": {
            "contractNegotiationId": NEGOTIATION,
            "contractAgreementId": LOCAL_AGREEMENT,
            "assetId": ASSET,
            **payload,
        },
    }
    return await client.post("/webhooks/contract-negotiation", json=body, headers=WEBHOOK)


@pytest.mark.asyncio
async def test_finalized_correlates_on_the_shared_id(client, correlated):
    """`dspAgreementId`, not `contractAgreementId`.

    The two are different strings and only the first is one the counterparty
    also holds — which is the entire reason `EDCL-06` had to settle it. Getting
    this wrong produces a trace backend where each side's spans are labelled with
    an id the other side has never seen, and nothing says so.
    """
    r = await _post(
        client,
        "CONTRACT_NEGOTIATION_FINALIZED",
        dspAgreementId=SHARED_AGREEMENT,
        providerId="did:web:rec.dataspaces.localhost",
        consumerId="did:web:third-party.dataspaces.localhost",
        policy={},
    )
    assert r.status_code == 200
    assert correlated == [SHARED_AGREEMENT], (
        f"correlated on {correlated!r}; the local id is {LOCAL_AGREEMENT!r} and "
        "the counterparty does not hold it"
    )


@pytest.mark.asyncio
async def test_a_state_before_finalized_correlates_on_nothing(client, correlated):
    """There is no agreement before one is signed, so there is nothing to
    correlate on — and a placeholder would join unrelated traces."""
    r = await _post(client, "CONTRACT_NEGOTIATION_REQUESTED")
    assert r.status_code == 200
    assert correlated == [None]


@pytest.mark.asyncio
async def test_correlation_happens_before_the_work_not_after(client, correlated):
    """Ordering is the whole value.

    The attribute is stamped by a span processor `on_start`, so it reaches only
    spans opened *after* the call. Correlating at the end of the handler would
    leave the agreement write, the provenance emission and every outbound call —
    the spans anyone would actually look for — unlabelled, while the handler's
    own span looked correctly tagged.
    """
    from connector.api.v1 import webhooks as module
    import inspect

    source = inspect.getsource(module.contract_negotiation_event)
    correlate_at = source.index("correlate_agreement(")
    assert correlate_at < source.index("upsert_agreement("), (
        "correlate_agreement runs after the work it is supposed to label"
    )
