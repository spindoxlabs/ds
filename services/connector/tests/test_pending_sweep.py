"""§6.2 — the deadline on a negotiation parked waiting for a person.

A parked negotiation waits on a data subject, and a data subject may never
answer. The sweep is what stops that from being permanent, so what it does and
— more importantly — what it refuses to do needs pinning down: one silent
subject must not cancel a request another subject has already granted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ConsentRequestORM
from connector.services.pending_sweep import (
    EXPIRED,
    expire_pending_asks,
    parse_duration,
    sweep_once,
)

NEGOTIATION = "neg-001"
DATASET = "datasets.silver.meters"
CONSUMER = "did:web:consumer.dataspaces.localhost"
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def _ask(subject: str, *, age_days: int, status: str = "pending", negotiation=NEGOTIATION):
    return ConsentRequestORM(
        subject_id=subject,
        consumer_id=CONSUMER,
        dataset_id=DATASET,
        purpose=["FlexibilityResearch"],
        status=status,
        requested_at=NOW - timedelta(days=age_days),
        negotiation_id=negotiation,
        correlation_id="consumer-side-id",
        transfer_ids=[],
    )


async def _seed(session_factory, *rows):
    async with session_factory() as session:
        for row in rows:
            session.add(row)
        await session.commit()


async def _statuses(session_factory) -> dict[str, str]:
    async with session_factory() as session:
        result = await session.execute(
            select(ConsentRequestORM.subject_id, ConsentRequestORM.status)
        )
        return dict(result.all())


# ── Duration parsing ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "value,expected",
    [
        ("P30D", timedelta(days=30)),
        ("PT12H", timedelta(hours=12)),
        ("P1DT6H30M", timedelta(days=1, hours=6, minutes=30)),
    ],
)
def test_parse_duration(value, expected):
    assert parse_duration(value) == expected


@pytest.mark.parametrize("value", ["P1Y", "P6M", "30", "", "PT"])
def test_ambiguous_or_malformed_durations_are_refused(value):
    """Years and months have no fixed length.

    A deadline that means something different in February than in March is one
    nobody can reason about, so it is rejected at startup rather than silently
    drifting.
    """
    with pytest.raises(ValueError):
        parse_duration(value)


# ── Expiry ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unanswered_ask_expires_and_kills_the_negotiation(session_factory):
    await _seed(session_factory, _ask("sub-quiet", age_days=31))

    async with session_factory() as session:
        dead = await expire_pending_asks(session, timedelta(days=30), now=NOW)

    assert list(dead) == [NEGOTIATION]
    assert await _statuses(session_factory) == {"sub-quiet": EXPIRED}


@pytest.mark.asyncio
async def test_expiry_is_not_a_refusal(session_factory):
    """``expired`` and ``rejected`` are different facts.

    A refusal is a person exercising a choice and is evidence of one; an expiry
    is the absence of a decision. Collapsing them would put a refusal in the
    record of someone who never said anything.
    """
    await _seed(session_factory, _ask("sub-quiet", age_days=31))
    async with session_factory() as session:
        await expire_pending_asks(session, timedelta(days=30), now=NOW)

    assert (await _statuses(session_factory))["sub-quiet"] == EXPIRED


@pytest.mark.asyncio
async def test_ask_within_the_ttl_is_left_alone(session_factory):
    await _seed(session_factory, _ask("sub-thinking", age_days=29))

    async with session_factory() as session:
        dead = await expire_pending_asks(session, timedelta(days=30), now=NOW)

    assert dead == {}
    assert (await _statuses(session_factory))["sub-thinking"] == "pending"


@pytest.mark.asyncio
async def test_a_grant_keeps_the_negotiation_alive(session_factory):
    """One silent subject must not cancel what another already granted.

    The consent constraint passes as soon as anybody is in the pool, so this
    negotiation is resumable — the quiet subject's ask still expires, but the
    negotiation is not reported dead.
    """
    await _seed(
        session_factory,
        _ask("sub-quiet", age_days=31),
        _ask("sub-granted", age_days=31, status="granted"),
    )

    async with session_factory() as session:
        dead = await expire_pending_asks(session, timedelta(days=30), now=NOW)

    assert dead == {}
    statuses = await _statuses(session_factory)
    assert statuses["sub-quiet"] == EXPIRED
    assert statuses["sub-granted"] == "granted"


@pytest.mark.asyncio
async def test_a_still_pending_ask_keeps_the_negotiation_alive(session_factory):
    """Subjects answer at their own pace; the deadline is per ask, not per pool."""
    await _seed(
        session_factory,
        _ask("sub-quiet", age_days=31),
        _ask("sub-recent", age_days=2),
    )

    async with session_factory() as session:
        dead = await expire_pending_asks(session, timedelta(days=30), now=NOW)

    assert dead == {}
    statuses = await _statuses(session_factory)
    assert statuses["sub-quiet"] == EXPIRED
    assert statuses["sub-recent"] == "pending"


@pytest.mark.asyncio
async def test_rows_with_no_negotiation_are_not_swept(session_factory):
    """A standing share provisioned at onboarding has no deadline.

    Only an ask raised *because* a negotiation is parked has one — nothing is
    blocked on a subject who simply has not visited their sharing settings.
    """
    await _seed(session_factory, _ask("sub-standing", age_days=400, negotiation=None))

    async with session_factory() as session:
        dead = await expire_pending_asks(session, timedelta(days=30), now=NOW)

    assert dead == {}
    assert (await _statuses(session_factory))["sub-standing"] == "pending"


# ── The full pass ────────────────────────────────────────────────────────────

class _RecordingEdc:
    def __init__(self, fail: bool = False):
        self.terminated: list[tuple[str, str]] = []
        self.fail = fail

    async def terminate_negotiation(self, negotiation_id: str, reason: str) -> None:
        if self.fail:
            raise RuntimeError("EDC unreachable")
        self.terminated.append((negotiation_id, reason))


@pytest.mark.asyncio
async def test_sweep_terminates_the_dead_negotiation(session_factory):
    await _seed(session_factory, _ask("sub-quiet", age_days=31))
    edc = _RecordingEdc()

    terminated = await sweep_once(session_factory, edc, timedelta(days=30), now=NOW)

    assert terminated == 1
    assert edc.terminated[0][0] == NEGOTIATION


@pytest.mark.asyncio
async def test_a_failed_termination_leaves_the_negotiation_for_the_next_pass(
    session_factory,
):
    """The rows stay expired, so the next pass finds the same dead negotiation.

    Retrying is what makes an unreachable EDC a delay rather than a negotiation
    parked for good.
    """
    await _seed(session_factory, _ask("sub-quiet", age_days=31))

    failing = _RecordingEdc(fail=True)
    assert await sweep_once(session_factory, failing, timedelta(days=30), now=NOW) == 0

    edc = _RecordingEdc()
    assert await sweep_once(session_factory, edc, timedelta(days=30), now=NOW) == 1
    assert edc.terminated[0][0] == NEGOTIATION


@pytest.mark.asyncio
async def test_a_terminated_negotiation_is_not_swept_again(session_factory):
    """Once dealt with, it stays dealt with.

    "No pending and no granted ask" never becomes false again, so without the
    closed marker every past negotiation would be re-terminated on every pass,
    forever.
    """
    await _seed(session_factory, _ask("sub-quiet", age_days=31))

    edc = _RecordingEdc()
    assert await sweep_once(session_factory, edc, timedelta(days=30), now=NOW) == 1
    assert await sweep_once(session_factory, edc, timedelta(days=30), now=NOW) == 0
    assert len(edc.terminated) == 1
