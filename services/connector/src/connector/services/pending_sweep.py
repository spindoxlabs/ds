"""Expire consent asks that nobody ever answered, and the negotiations they park.

A negotiation parked by ``ConsentPendingGuard`` waits on a person, and a person
may simply never answer. Without a deadline that negotiation sits in
``REQUESTED`` forever, holding a consumer's request open on a decision that is
not coming and leaving an unanswered question on a subject's list indefinitely.

**Why this is a setting and not a policy term.** The nearest upstream mechanism,
``ContractExpiryCheckFunction``, evaluates ``edc:inForceDate`` — *when an
agreement is valid*, not how long a negotiation may wait. There is no ODRL
operand for a negotiation deadline, and inventing one would be exactly the
open-ended policy property EDC's maintainers declined. So it is connector
configuration: ``CONNECTOR_CONSENT_PENDING_TTL`` (plan §6.2's
``ds.consent.pending.ttl``), default 30 days.

Expiry is not a refusal. The consent rows are marked ``expired``, not
``rejected`` — nobody decided anything — and DSP explicitly permits a new
negotiation after ``TERMINATED``, so a consumer that still wants the data simply
asks again.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import ConsentRequestORM

log = logging.getLogger(__name__)

#: Status for an ask that ran out of time. Distinct from ``rejected`` on
#: purpose: a refusal is a person exercising a choice and is evidence; an
#: expiry is the absence of one.
EXPIRED = "expired"

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_duration(value: str) -> timedelta:
    """Parse the day/time subset of ISO 8601 durations.

    Deliberately no ``Y`` or ``M`` (months): both are ambiguous in length, and a
    consent deadline that means different things in February than in March is a
    deadline nobody can reason about. ``P30D`` and ``PT12H`` are the shapes this
    setting is actually for.
    """
    match = _ISO_DURATION.match(value.strip().upper())
    if not match or not any(match.groupdict().values()):
        raise ValueError(
            f"Invalid consent pending TTL {value!r} — expected an ISO 8601 "
            "duration in days/hours/minutes/seconds, e.g. P30D or PT12H"
        )
    parts = {key: int(raw) for key, raw in match.groupdict().items() if raw}
    return timedelta(**parts)


async def expire_pending_asks(
    session: AsyncSession,
    ttl: timedelta,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    """Mark timed-out asks expired; report the negotiations left with nothing.

    Two steps, deliberately separate:

    1. every ask past its TTL becomes ``expired``;
    2. every *still-open* negotiation that now has neither a pending nor a
       granted ask is reported dead.

    Step 2 is not restricted to negotiations step 1 just touched. It cannot be:
    "no pending and no granted ask" is a property of the consent rows, so once a
    termination fails the sweep has to be able to find that negotiation again on
    the next pass — otherwise one unreachable EDC would park it for good.
    ``negotiation_closed_at`` is what then stops the retry once it succeeds.

    A negotiation where somebody *did* grant is already resumable and is never
    reported: one silent subject must not cancel what another agreed to.

    Returns ``{negotiation_id: [consent_id, ...]}``.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - ttl

    result = await session.execute(
        select(ConsentRequestORM).where(
            ConsentRequestORM.negotiation_id.is_not(None),
            ConsentRequestORM.negotiation_closed_at.is_(None),
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return {}

    for row in rows:
        if row.status != "pending":
            continue
        requested_at = row.requested_at
        if requested_at is None:
            continue
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)
        if requested_at > cutoff:
            continue
        row.status = EXPIRED
        row.decided_at = now
        row.revocation_reason = "No decision within the consent request TTL"

    by_negotiation: dict[str, list[ConsentRequestORM]] = {}
    for row in rows:
        by_negotiation.setdefault(row.negotiation_id, []).append(row)

    dead = {
        negotiation_id: [row.id for row in group]
        for negotiation_id, group in by_negotiation.items()
        if not any(row.status in ("pending", "granted") for row in group)
    }

    await session.commit()
    return dead


async def close_negotiation_asks(
    session: AsyncSession, negotiation_id: str, now: datetime | None = None
) -> None:
    """Record that this negotiation is over, so the sweep stops revisiting it."""
    result = await session.execute(
        select(ConsentRequestORM).where(
            ConsentRequestORM.negotiation_id == negotiation_id,
            ConsentRequestORM.negotiation_closed_at.is_(None),
        )
    )
    closed_at = now or datetime.now(timezone.utc)
    for row in result.scalars().all():
        row.negotiation_closed_at = closed_at
    await session.commit()


async def sweep_once(
    session_factory: async_sessionmaker[AsyncSession],
    provider_edc,
    ttl: timedelta,
    now: datetime | None = None,
) -> int:
    """One pass. Returns the number of negotiations terminated."""
    async with session_factory() as session:
        dead = await expire_pending_asks(session, ttl, now=now)

    terminated = 0
    for negotiation_id, consent_ids in dead.items():
        log.info(
            "Consent TTL expired for negotiation %s (%d unanswered ask(s)) — terminating",
            negotiation_id,
            len(consent_ids),
        )
        if provider_edc is None:
            continue
        try:
            await provider_edc.terminate_negotiation(
                negotiation_id, "Consent request expired without a decision"
            )
        except Exception as exc:
            # Leave it open: the next pass will find it again and retry, which
            # is what makes an unreachable EDC a delay rather than a negotiation
            # parked for good.
            log.warning("Could not terminate expired negotiation %s: %s", negotiation_id, exc)
            continue
        async with session_factory() as session:
            await close_negotiation_asks(session, negotiation_id, now=now)
        terminated += 1
    return terminated


async def run_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    provider_edc,
    ttl: timedelta,
    interval_seconds: float,
) -> None:
    """Sweep forever, surviving its own failures.

    A crash in a background task that nothing restarts is worse than a slow
    sweep: the deadline would silently stop being enforced, and nothing about
    the running system would look wrong.
    """
    log.info(
        "Consent pending sweeper started (ttl=%s, interval=%ss)", ttl, interval_seconds
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await sweep_once(session_factory, provider_edc, ttl)
        except asyncio.CancelledError:
            log.info("Consent pending sweeper stopped")
            raise
        except Exception:
            log.exception("Consent pending sweep failed; continuing")
