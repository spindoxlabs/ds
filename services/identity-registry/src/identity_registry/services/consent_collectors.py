"""Consent collectors — which organisations a holder accepts consent from.

Plan `a-collector-registers-consent-at-the-holder`. A person consents where they
are a member (an energy community); the organisation holding their data (a grid
operator) registers that consent on its own connector, so its data plane needs no
call back to the community. The holder's connector accepts such a registration
only from an organisation named here, and only for that organisation's members.

**Registry data, not connector configuration** (the maintainer, 2026-09-17). Who
may speak for whose members is a governance fact about two organisations, and the
anchor already holds both of them. The connector reads it through the narrow
check route and caches the answer; a change here tells the connectors to drop
that cache (`registry_notify`).

Three properties, each easy to lose:

- **A holder always collects for itself.** Its own organisation registering its
  own members' consent is not a relation anybody has to write down, and a check
  asked about the pair `(X, X)` says so.
- **Revocation marks, never deletes.** A consent row names the collector that
  registered it; a relation that vanished would leave that evidence unexplained.
- **The answer names the collector's owner.** The connector checks membership
  against the collecting organisation (`D-21`), and the registry is what knows
  which owner a DID belongs to. An unverified or unknown owner is not accepted:
  nobody can say whose members it would be speaking for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ConsentCollector, Owner, Participant

ACTIVE = "active"
REVOKED = "revoked"


class CollectorError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class CollectorCheck:
    """The answer a holder's connector acts on."""

    holder_did: str
    collector_did: str
    accepted: bool
    #: The owner id the collector DID belongs to — what membership is checked
    #: against. `None` when no owner carries the DID.
    collector_owner: str | None
    reason: str


async def owner_for_did(db: AsyncSession, did: str) -> Owner | None:
    """The owner whose `did` is *did*, or `None`. Two owners on one DID is `None`.

    Picking one of two would hand a connector a membership roster by row order.
    """
    rows = (await db.execute(select(Owner).where(Owner.did == did))).scalars().all()
    return rows[0] if len(rows) == 1 else None


async def check(
    db: AsyncSession, holder_did: str, collector_did: str
) -> CollectorCheck:
    owner = await owner_for_did(db, collector_did)
    owner_id = owner.id if owner is not None else None
    if holder_did == collector_did:
        return CollectorCheck(
            holder_did, collector_did, True, owner_id, "a holder collects for itself"
        )
    row = await _get(db, holder_did, collector_did)
    if row is None or row.status != ACTIVE:
        return CollectorCheck(
            holder_did, collector_did, False, owner_id, "not an accepted collector"
        )
    if owner is None or owner.status != "verified":
        # The relation stands and the organisation behind it does not: a
        # suspended or unknown owner speaks for nobody's members.
        return CollectorCheck(
            holder_did,
            collector_did,
            False,
            owner_id,
            "the collector is not a verified organisation",
        )
    return CollectorCheck(
        holder_did, collector_did, True, owner_id, "an accepted collector"
    )


async def _get(
    db: AsyncSession, holder_did: str, collector_did: str
) -> ConsentCollector | None:
    return (
        await db.execute(
            select(ConsentCollector).where(
                ConsentCollector.holder_did == holder_did,
                ConsentCollector.collector_did == collector_did,
            )
        )
    ).scalar_one_or_none()


async def add(
    db: AsyncSession,
    *,
    holder_did: str,
    collector_did: str,
    added_by: str | None = None,
) -> ConsentCollector:
    """Accept *collector_did* for *holder_did*. Idempotent; re-activates a revoked pair.

    The holder must be an active participant (it has a connector to register at)
    and the collector a verified owner (it has members to speak for). The pair
    `(X, X)` is refused: a holder always collects for itself, and a row saying so
    would be a second place the same fact lives.
    """
    if holder_did == collector_did:
        raise CollectorError(
            "a holder always collects for itself — there is nothing to record"
        )
    participant = (
        await db.execute(
            select(Participant).where(
                Participant.did == holder_did, Participant.active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if participant is None:
        raise CollectorError(f"{holder_did} is not an active participant")
    owner = await owner_for_did(db, collector_did)
    if owner is None or owner.status != "verified":
        raise CollectorError(
            f"{collector_did} is not the DID of exactly one verified organisation"
        )

    now = datetime.now(UTC)
    row = await _get(db, holder_did, collector_did)
    if row is None:
        row = ConsentCollector(
            holder_did=holder_did,
            collector_did=collector_did,
            status=ACTIVE,
            added_by=added_by,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    elif row.status != ACTIVE:
        row.status = ACTIVE
        row.revoked_at = None
        row.revocation_reason = None
        row.added_by = added_by or row.added_by
        row.updated_at = now
    await db.flush()
    return row


async def revoke(
    db: AsyncSession, *, holder_did: str, collector_did: str, reason: str
) -> ConsentCollector:
    """Mark the pair revoked. The reason is required; an unknown pair is a 404."""
    if not reason or not reason.strip():
        raise CollectorError("a revocation needs a reason")
    row = await _get(db, holder_did, collector_did)
    if row is None:
        raise CollectorError("no such collector relation", status_code=404)
    if row.status != REVOKED:
        now = datetime.now(UTC)
        row.status = REVOKED
        row.revoked_at = now
        row.revocation_reason = reason.strip()
        row.updated_at = now
        await db.flush()
    return row


async def list_relations(
    db: AsyncSession, *, holder_did: str | None = None, include_revoked: bool = True
) -> list[ConsentCollector]:
    stmt = select(ConsentCollector)
    if holder_did:
        stmt = stmt.where(ConsentCollector.holder_did == holder_did)
    if not include_revoked:
        stmt = stmt.where(ConsentCollector.status == ACTIVE)
    stmt = stmt.order_by(ConsentCollector.holder_did, ConsentCollector.collector_did)
    return list((await db.execute(stmt)).scalars().all())
