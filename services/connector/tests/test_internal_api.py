"""Tests for /internal endpoints."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.config import get_settings
from connector.db.models import ConsentRequestORM
from connector.services.agreement_service import upsert_agreement
from connector.services.consent_service import create_consent_request
from tests import make_headers

HEADERS = make_headers(scope="connector.internal")

EDC = get_settings().edc_rec_management_url.rstrip("/")


@pytest.mark.asyncio
@respx.mock
async def test_agreement_status_not_found(client):
    """A 404 from the EDC is a real negative — the agreement does not exist."""
    respx.get(f"{EDC}/v3/contractagreements/nonexistent").mock(
        return_value=httpx.Response(404)
    )
    r = await client.get("/internal/agreements/nonexistent/status", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.rule("X-10")
@pytest.mark.asyncio
@respx.mock
async def test_agreement_status_unreachable_edc_is_not_a_404(client):
    """`CR-4` — an undecidable answer must not be reported as a definite one.

    This is the regression the swallow-everything handler produced: a refused
    connection came back as "agreement not found", which a PEP caches as a
    negative fact about the agreement rather than as a failure to ask.
    """
    respx.get(f"{EDC}/v3/contractagreements/urn:uuid:x").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    r = await client.get("/internal/agreements/urn:uuid:x/status", headers=HEADERS)
    assert r.status_code == 503
    assert "unreachable" in r.json()["detail"].lower()


@pytest.mark.rule("X-10")
@pytest.mark.asyncio
@respx.mock
async def test_agreement_status_edc_5xx_is_not_a_404(client):
    """A 500 from the EDC is not evidence that the agreement is absent."""
    respx.get(f"{EDC}/v3/contractagreements/urn:uuid:x").mock(
        return_value=httpx.Response(500, text="boom")
    )
    r = await client.get("/internal/agreements/urn:uuid:x/status", headers=HEADERS)
    assert r.status_code == 503


@pytest.mark.rule("X-6", "X-10")
@pytest.mark.asyncio
@respx.mock
async def test_transfer_status_unreachable_edc_denies_and_says_so(client):
    """Deny, as `CR-4` requires — but never as `transfer_not_found`.

    The deny shape was already correct here; the *reason* was not. Reporting a
    definite "no such transfer" for a connection failure is the fact an operator
    would use to conclude the consumer never started one.
    """
    respx.post(f"{EDC}/v3/transferprocesses/request").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    r = await client.get("/internal/transfers/tp-unknown/status", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is False
    assert body["reason"] == "edc_unreachable"


@pytest.mark.rule("X-10")
@pytest.mark.asyncio
@respx.mock
async def test_transfer_status_empty_result_is_not_found(client):
    """An EDC that answers with no match is a real negative."""
    respx.post(f"{EDC}/v3/transferprocesses/request").mock(
        return_value=httpx.Response(200, json=[])
    )
    r = await client.get("/internal/transfers/tp-unknown/status", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"active": False, "reason": "transfer_not_found"}


@pytest.mark.asyncio
async def test_agreement_status_found(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await upsert_agreement(
                session,
                agreement_id="urn:uuid:test-agreement-001",
                asset_id="https://provider.example/datasets/meters",
                consumer_id="consumer",
                provider_id="provider",
                policy_snapshot={"@type": "odrl:Set"},
                agreed_at=datetime.now(UTC),
            )

    r = await client.get(
        "/internal/agreements/urn:uuid:test-agreement-001/status",
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["asset_id"] == "https://provider.example/datasets/meters"
    assert body["consumer_id"] == "consumer"


@pytest.mark.rule("X-6b")
@pytest.mark.asyncio
async def test_consent_check_no_consent(client):
    r = await client.get(
        "/internal/consent/check",
        params={
            "subject_id": "sub-001",
            "dataset_id": "datasets.silver.meters",
            "consumer_id": "consumer",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["consent_active"] is False


@pytest.mark.rule("D-15")
@pytest.mark.asyncio
async def test_consent_check_uses_latest_status(engine, client):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            session.add_all(
                [
                    ConsentRequestORM(
                        subject_id="sub-001",
                        dataset_id="datasets.silver.meters",
                        consumer_id="consumer",
                        status="granted",
                        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
                        decided_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
                        purpose=[],
                        transfer_ids=[],
                    ),
                    ConsentRequestORM(
                        subject_id="sub-001",
                        dataset_id="datasets.silver.meters",
                        consumer_id="consumer",
                        status="revoked",
                        requested_at=datetime(2026, 1, 2, tzinfo=UTC),
                        decided_at=datetime(2026, 1, 2, 1, tzinfo=UTC),
                        revoked_at=datetime(2026, 1, 2, 2, tzinfo=UTC),
                        purpose=[],
                        transfer_ids=[],
                    ),
                ]
            )

    r = await client.get(
        "/internal/consent/check",
        params={
            "subject_id": "sub-001",
            "dataset_id": "datasets.silver.meters",
            "consumer_id": "consumer",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["consent_active"] is False

    r = await client.get(
        "/internal/consent/check",
        params={
            "dataset_id": "datasets.silver.meters",
            "consumer_id": "consumer",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["subject_ids"] == []


@pytest.mark.asyncio
async def test_create_consent_request_reuses_open_request(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            first = await create_consent_request(
                session,
                subject_id="sub-001",
                dataset_id="datasets.silver.meters",
                consumer_id="consumer",
            )
            second = await create_consent_request(
                session,
                subject_id="sub-001",
                dataset_id="datasets.silver.meters",
                consumer_id="consumer",
            )

        result = await session.execute(
            select(func.count()).select_from(ConsentRequestORM)
        )

    assert second.id == first.id
    assert result.scalar_one() == 1
