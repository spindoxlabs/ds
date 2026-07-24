"""§6.7 — the ``should_ask`` / ``pending_request_id`` projection.

``GET /internal/consent/check`` is the one place consent is decided. The pending
guard reads two extra fields off the same answer rather than reconstructing the
circle rules in Java, so what those fields mean has to be pinned down here:

- ``should_ask`` — *if consent is absent, is that a question for a person?*
  False when nobody can be asked (no consent gate) or when the requester is
  already covered as a processor and must be disclosed instead (§6.3).
- ``pending_request_id`` — an ask already outstanding for the tuple, so a
  re-negotiating consumer reattaches instead of asking the same people twice.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from tests import make_headers

INTERNAL = make_headers(scope="connector.internal")

CONSENTED_DATASET = "datasets.silver.meters"
OPEN_DATASET = "datasets.gold.weather"
CONSUMER = "did:web:consumer.dataspaces.localhost"
SUBJECT = "did:web:users.dataspaces.localhost:sub-001"
PURPOSE = "FlexibilityResearch"


@pytest.fixture(autouse=True)
def _outside_the_circle(monkeypatch):
    """No identity-registry in a unit run, so capacity is unprovable.

    That is the production default too until the registry exposes agreements,
    and it resolves to *outside the circle* — which asks rather than assumes.
    Tests that want the opposite stub :func:`circle.is_covered_processor`.
    """
    async def _capacity(*_args, **_kwargs):
        return None

    monkeypatch.setattr("connector.services.circle._agreement_capacity", _capacity)


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _check(client, **params):
    response = await client.get(
        "/internal/consent/check",
        params={"consumer_id": CONSUMER, **params},
        headers=INTERNAL,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_open_dataset_is_never_a_question(client):
    """No consent gate means no data subject, so there is nobody to ask."""
    body = await _check(client, dataset_id=OPEN_DATASET)
    assert body["should_ask"] is False
    assert body["pending_request_id"] is None


@pytest.mark.asyncio
async def test_consent_gated_dataset_asks_when_capacity_is_unprovable(client):
    body = await _check(client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE)
    assert body["should_ask"] is True


@pytest.mark.asyncio
async def test_covered_processor_is_disclosed_not_asked(client, monkeypatch):
    """A processor of the offer's controller acts under a DPA (Art. 28).

    The controller has not changed and neither has the processing operation, so
    asking again would imply a choice that does not exist.
    """
    async def _covered(offers, **_kwargs):
        assert [offer.id for offer in offers] == ["test-flexibility"]
        return True

    monkeypatch.setattr("connector.services.circle.is_covered_processor", _covered)

    body = await _check(client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE)
    assert body["should_ask"] is False


@pytest.mark.asyncio
async def test_should_ask_does_not_depend_on_consent_being_absent(client):
    """It answers "would this be a question", not "is consent missing".

    The guard needs both facts separately: it parks on absent consent, but only
    when the absence is something a person can resolve.
    """
    body = await _check(
        client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE, subject_id=SUBJECT
    )
    assert body["consent_active"] is False
    assert body["should_ask"] is True


@pytest.mark.asyncio
async def test_pending_ask_is_reported_so_a_retry_reattaches(client, session_factory):
    async with session_factory() as session:
        row = ConsentRequestORM(
            subject_id=SUBJECT,
            consumer_id=CONSUMER,
            dataset_id=CONSENTED_DATASET,
            purpose=[PURPOSE],
            status="pending",
            requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            transfer_ids=[],
        )
        session.add(row)
        await session.commit()
        pending_id = row.id

    body = await _check(client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE)
    assert body["pending_request_id"] == pending_id
    # Still a question — the ask exists but nobody has answered it.
    assert body["should_ask"] is True


@pytest.mark.asyncio
async def test_a_settled_ask_is_not_reported_as_pending(client, session_factory):
    """Only ``pending`` reattaches. A rejected ask is a decision, not a queue."""
    async with session_factory() as session:
        session.add(
            ConsentRequestORM(
                subject_id=SUBJECT,
                consumer_id=CONSUMER,
                dataset_id=CONSENTED_DATASET,
                purpose=[PURPOSE],
                status="rejected",
                requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                decided_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                transfer_ids=[],
            )
        )
        await session.commit()

    body = await _check(client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE)
    assert body["pending_request_id"] is None


@pytest.mark.asyncio
async def test_pending_ask_for_another_purpose_does_not_match(client, session_factory):
    """Purpose matching is ``odrl:isA``, in the same direction consent uses.

    An outstanding question about one purpose is not an outstanding question
    about an unrelated one, so the second purpose still has to be asked.
    """
    async with session_factory() as session:
        session.add(
            ConsentRequestORM(
                subject_id=SUBJECT,
                consumer_id=CONSUMER,
                dataset_id=CONSENTED_DATASET,
                purpose=["IncentiveCalculation"],
                status="pending",
                requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                transfer_ids=[],
            )
        )
        await session.commit()

    body = await _check(client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE)
    assert body["pending_request_id"] is None


@pytest.mark.asyncio
async def test_existing_callers_keep_their_fields(client):
    """The PEP and the negotiation function must not notice this change."""
    pool = await _check(client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE)
    assert pool["subject_ids"] == []

    named = await _check(
        client, dataset_id=CONSENTED_DATASET, purpose=PURPOSE, subject_id=SUBJECT
    )
    assert named["consent_active"] is False
    assert "reason" in named
    assert "legal_basis" in named
