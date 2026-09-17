"""`D-14` on the audience read, against a migrated PostgreSQL (#37).

The unit tests in `tests/test_wildcard_admission.py` stub `circle`'s network
leaves and run on SQLite. This test keeps `circle` whole and fakes only the
transport, answering in the identity registry's real response shapes. It runs
the consent query on the schema the migrations build.

The case is the one the live `onboarding-seam` flow tripped on: a participant
whose agreement declares `capacity: processor` but which is not a member of the
offer's controller. The offer's `admitted_by` requires that membership, so the
standing wildcard does not reach it, while the controller still reads the
subject.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.dependencies import get_db
from connector.main import create_app
from connector.services import circle
from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    set_subject_data_sharing,
)
from tests import make_headers

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]

GATED = "datasets.silver.meters"
SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
CONTROLLER = "did:web:example-org.dataspaces.localhost"
PROCESSOR = "did:web:service-provider.dataspaces.localhost"
AUDIENCE = make_headers(scope="connector.consent.audience")

REAL_ASYNC_CLIENT = httpx.AsyncClient


def _registry(member: bool) -> httpx.MockTransport:
    """The identity registry, as `circle` reads it: three routes."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/agreements/current":
            return httpx.Response(
                200,
                json={
                    "participant_did": request.url.params["participant_did"],
                    "agreement_id": "dataspace-participation",
                    "capacity": circle.PROCESSOR,
                },
            )
        if path == "/memberships/check":
            return httpx.Response(200, json={"member": member})
        if path == "/credentials/check":
            return httpx.Response(200, json={"holds": True})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class _Owners:
    async def by_id(self, alias: str):
        return SimpleNamespace(did=CONTROLLER) if alias == "example-org" else None


async def _migrated(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=UNIT_DIR,
        env={**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def _audience(client: AsyncClient, consumer: str) -> list[list[str]]:
    response = await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": consumer},
        headers=AUDIENCE,
    )
    assert response.status_code == 200, response.text
    return [d["subject_ids"] for d in response.json()["datasets"]]


@pytest.mark.parametrize(
    "member,processor_reads",
    [(False, [[]]), (True, [[SUBJECT]])],
    ids=["processor-outside-admitted-by", "processor-inside-admitted-by"],
)
async def test_the_audience_is_bounded_by_the_offers_circle(
    empty_database, monkeypatch, member, processor_reads
):
    await _migrated(empty_database)
    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await set_subject_data_sharing(
                session,
                subject_id=SUBJECT,
                dataset_id=GATED,
                consumer_id=WILDCARD_CONSUMER,
                enabled=True,
                purpose=["FlexibilityResearch"],
                controller="example-org",
                offer_id="test-flexibility",
            )

        transport = _registry(member)

        def _client(**kwargs):
            kwargs.pop("transport", None)
            return REAL_ASYNC_CLIENT(transport=transport, **kwargs)

        monkeypatch.setattr(circle.httpx, "AsyncClient", _client)

        app = create_app()
        app.state.owners_registry = _Owners()
        app.state.ir_token_provider = None

        async def _db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = _db

        async with REAL_ASYNC_CLIENT(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert await _audience(client, CONTROLLER) == [[SUBJECT]]
            assert await _audience(client, PROCESSOR) == processor_reads
    finally:
        await engine.dispose()
