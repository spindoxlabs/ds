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

- **A holder always collects for itself** — while it is a verified
  organisation. Its own organisation registering its own members' consent is
  not a relation anybody has to write down, and a check asked about the pair
  `(X, X)` says so; a suspended or unknown holder is not accepted (ADR-0026).
- **Revocation marks, never deletes.** A consent row names the collector that
  registered it; a relation that vanished would leave that evidence unexplained.
- **A revocation survives a re-add.** The anchor's bootstrap runs `collector add`
  on every start, so an `add` that revived a revoked pair undid every revocation
  at the next restart. `add` leaves a revoked pair as it is (and succeeds, so a
  declarative seed keeps working); lifting a revocation is `reinstate`, an
  explicit operation with a reason, recorded on the row.
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
        if owner is None or owner.status != "verified":
            # Collecting for itself is implicit, never a free pass: a suspended
            # holder speaks for nobody's members, its own included (ADR-0026).
            return CollectorCheck(
                holder_did,
                collector_did,
                False,
                owner_id,
                "the holder is not a verified organisation",
            )
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


async def get_relation(
    db: AsyncSession, holder_did: str, collector_did: str
) -> ConsentCollector | None:
    """The row for one pair, or ``None``."""
    return await _get(db, holder_did, collector_did)


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


async def _require_admissible(
    db: AsyncSession, holder_did: str, collector_did: str
) -> None:
    """What a pair in force needs: an active holder and a verified collector."""
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


@dataclass(frozen=True, slots=True)
class AddOutcome:
    """What `add` did: created the pair, found it in force, or found it revoked."""

    row: ConsentCollector
    created: bool

    @property
    def revoked(self) -> bool:
        return self.row.status != ACTIVE


def describe_revocation(row: ConsentCollector) -> str:
    """One line naming a revoked pair's revocation: by whom, when, why."""
    when = row.revoked_at.isoformat() if row.revoked_at else "an unrecorded time"
    return (
        f"revoked by {row.revoked_by or 'an unrecorded actor'} at {when}: "
        f"{row.revocation_reason or 'no reason recorded'}"
    )


async def add(
    db: AsyncSession,
    *,
    holder_did: str,
    collector_did: str,
    added_by: str | None = None,
) -> AddOutcome:
    """Accept *collector_did* for *holder_did*. Idempotent; **never revives**.

    The holder must be an active participant (it has a connector to register at)
    and the collector a verified owner (it has members to speak for). The pair
    `(X, X)` is refused: a holder always collects for itself, and a row saying so
    would be a second place the same fact lives.

    A pair already revoked is left exactly as it is and returned, so the caller
    can say that the pair it declared is not in force (`describe_revocation`).
    Not an error: the anchor's bootstrap re-adds its declared pairs on every
    start, and a revocation must neither be undone by that nor break it.
    Lifting a revocation is :func:`reinstate`.
    """
    await _require_admissible(db, holder_did, collector_did)
    row = await _get(db, holder_did, collector_did)
    if row is not None:
        return AddOutcome(row, created=False)
    now = datetime.now(UTC)
    row = ConsentCollector(
        holder_did=holder_did,
        collector_did=collector_did,
        status=ACTIVE,
        added_by=added_by,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return AddOutcome(row, created=True)


async def reinstate(
    db: AsyncSession,
    *,
    holder_did: str,
    collector_did: str,
    reason: str,
    reinstated_by: str | None = None,
) -> ConsentCollector:
    """Lift a revocation: the explicit counterpart `add` deliberately is not.

    The reason is required and kept on the row with who and when; an unknown
    pair is a 404; the pair must meet `add`'s preconditions again (an active
    holder, a verified collector), or the reinstatement would put in force a
    relation `add` would refuse. A pair already active is returned unchanged.
    The revocation it lifts stays on the row as history.
    """
    if not reason or not reason.strip():
        raise CollectorError("a reinstatement needs a reason")
    row = await _get(db, holder_did, collector_did)
    if row is None:
        raise CollectorError("no such collector relation", status_code=404)
    if row.status == ACTIVE:
        return row
    await _require_admissible(db, holder_did, collector_did)
    now = datetime.now(UTC)
    row.status = ACTIVE
    row.reinstated_at = now
    row.reinstated_by = reinstated_by
    row.reinstatement_reason = reason.strip()
    row.updated_at = now
    await db.flush()
    return row


async def revoke(
    db: AsyncSession,
    *,
    holder_did: str,
    collector_did: str,
    reason: str,
    revoked_by: str | None = None,
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
        row.revoked_by = revoked_by
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
