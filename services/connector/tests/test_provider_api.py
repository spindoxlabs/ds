"""``GET /provider/agreements`` — a producer's own contracts.

Found by the portal UI journeys: `/provider/contracts` was wired to
``/provider/transfers``, which returns raw EDC transfer processes in JSON-LD.
The page declared them as contract agreements and read ``agreement_id`` off
each one, so it rendered only while the list happened to be empty and threw a
500 on the first real transfer.

The fix is an endpoint that returns what the page always meant to show, gated so
a read-only producer can actually reach it.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ContractAgreementORM
from tests import make_headers

PROVIDER_READ = make_headers(scope="connector.provider.read")
PROVIDER = "did:web:provider.dataspaces.localhost"
OTHER_PROVIDER = "did:web:other.dataspaces.localhost"
CONSUMER = "did:web:consumer.dataspaces.localhost"


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def _agreement(**overrides) -> ContractAgreementORM:
    base = dict(
        agreement_id="agr-1",
        asset_id="datasets.silver.meters",
        consumer_id=CONSUMER,
        provider_id=PROVIDER,
        policy_snapshot={},
        agreed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return ContractAgreementORM(**base)


@pytest.mark.asyncio
async def test_provider_read_alone_can_list_agreements(client, session_factory):
    """A producer reading contracts over their own datasets is reading provider
    data. Requiring ``connector.history.read`` — which spans every party's
    activity — would lock a read-only producer out of their own."""
    async with session_factory() as session:
        session.add(_agreement())
        await session.commit()

    r = await client.get("/provider/agreements", headers=PROVIDER_READ)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["agreement_id"] for row in rows] == ["agr-1"]
    # The shape the page renders, not an EDC transfer process.
    assert rows[0]["asset_id"] == "datasets.silver.meters"
    assert rows[0]["consumer_id"] == CONSUMER
    assert "terminated_at" in rows[0]


@pytest.mark.asyncio
async def test_another_participants_agreements_are_not_listed(client, session_factory):
    """Scoped to this participant as provider, so a shared database never leaks
    a different provider's contracts into this view."""
    async with session_factory() as session:
        session.add(_agreement(agreement_id="mine"))
        session.add(_agreement(agreement_id="theirs", provider_id=OTHER_PROVIDER))
        await session.commit()

    rows = (await client.get("/provider/agreements", headers=PROVIDER_READ)).json()
    assert [row["agreement_id"] for row in rows] == ["mine"]


@pytest.mark.asyncio
async def test_active_only_excludes_terminated(client, session_factory):
    """"Active" is the absence of a termination, not a separate status column —
    the page derives its badge the same way."""
    async with session_factory() as session:
        session.add(_agreement(agreement_id="live"))
        session.add(
            _agreement(
                agreement_id="dead",
                terminated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                termination_reason="revoked by subject",
            )
        )
        await session.commit()

    everything = (await client.get("/provider/agreements", headers=PROVIDER_READ)).json()
    assert {row["agreement_id"] for row in everything} == {"live", "dead"}

    active = (
        await client.get("/provider/agreements?active_only=true", headers=PROVIDER_READ)
    ).json()
    assert [row["agreement_id"] for row in active] == ["live"]


@pytest.mark.asyncio
async def test_an_anonymous_caller_is_refused(client):
    r = await client.get("/provider/agreements")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_an_unrelated_scope_is_refused(client):
    """Authentication is not authorisation: a valid token without the provider
    grant must not read another participant's contract history."""
    r = await client.get(
        "/provider/agreements", headers=make_headers(scope="connector.consent.provision")
    )
    assert r.status_code == 403
