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

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ContractAgreementORM
from tests import make_headers

PROVIDER_READ = make_headers(scope="connector.provider.read")
PROVIDER = "did:web:rec.dataspaces.localhost"
OTHER_PROVIDER = "did:web:other.dataspaces.localhost"
CONSUMER = "did:web:third-party.dataspaces.localhost"


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
        agreed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return ContractAgreementORM(**base)


@pytest.mark.rule("C-15")
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


@pytest.mark.rule("C-16", "C-20")
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
    """ "Active" is the absence of a termination, not a separate status column —
    the page derives its badge the same way."""
    async with session_factory() as session:
        session.add(_agreement(agreement_id="live"))
        session.add(
            _agreement(
                agreement_id="dead",
                terminated_at=datetime(2026, 2, 1, tzinfo=UTC),
                termination_reason="revoked by subject",
            )
        )
        await session.commit()

    everything = (
        await client.get("/provider/agreements", headers=PROVIDER_READ)
    ).json()
    assert {row["agreement_id"] for row in everything} == {"live", "dead"}

    active = (
        await client.get("/provider/agreements?active_only=true", headers=PROVIDER_READ)
    ).json()
    assert [row["agreement_id"] for row in active] == ["live"]


@pytest.mark.rule("C-15", "C-17")
@pytest.mark.asyncio
async def test_an_anonymous_caller_is_refused(client):
    r = await client.get("/provider/agreements")
    assert r.status_code in (401, 403)


@pytest.mark.rule("C-15", "C-17")
@pytest.mark.asyncio
async def test_an_unrelated_scope_is_refused(client):
    """Authentication is not authorisation: a valid token without the provider
    grant must not read another participant's contract history."""
    r = await client.get(
        "/provider/agreements",
        headers=make_headers(scope="connector.consent.provision"),
    )
    assert r.status_code == 403


@pytest.mark.rule("M-10")
@pytest.mark.asyncio
async def test_sync_drops_the_cached_consent_vocabulary(engine, monkeypatch):
    """The vocabulary gates consent *writes*, not just what is displayed.

    It is cached for the process lifetime by design. Without an invalidation on
    sync, an offer contributed since startup is accepted by the sync and then
    rejected as unknown by `POST /consent/my/shares`, and `/ns/sharing-offers`
    keeps advertising a `consent_text_version` nobody publishes any more.

    Builds its own app so `get_provider_edc` can be overridden — the shared
    `client` fixture does not expose one.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from connector.dependencies import get_db, get_provider_edc
    from connector.main import create_app
    from connector.schemas.edc import SyncResult
    from connector.services import consent_vocabulary as vocab

    calls: list[int] = []
    monkeypatch.setattr(vocab, "reset_caches", lambda: calls.append(1))

    async def _fake_sync(*_args, **_kwargs):
        return SyncResult()

    monkeypatch.setattr(
        "connector.services.provider_service.sync_governance", _fake_sync
    )

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_provider_edc] = lambda: object()
    app.state.prov = None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/provider/sync",
            json={},
            headers=make_headers(scope="connector.provider.write"),
        )

    assert resp.status_code == 200, resp.text
    assert calls, "sync did not invalidate the consent vocabulary"
