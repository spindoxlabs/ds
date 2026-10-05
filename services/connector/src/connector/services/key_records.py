"""The holder's records of who a data key belongs to, and on whose assertion (ADR-0027).

A collector registering a member's decision at this connector sends the member's
typed data keys (``pod:…``) and, with them, its **assertion** that the keys are
the member's: which terms it accepted, how it verified, when, and digests of the
evidence it holds. This module keeps what the holder needs to reconstruct that
later, and to act on it:

- the **recipes** — :func:`assertion_ref`, :func:`keys_digest`,
  :func:`decision_ref` — each a SHA-256 an auditor can recompute from the
  holder's own records without opening a key (they hash the keyed blind index,
  ``connector.db.sealed.blind_index``, never the key);
- the **policy** a holder applies to a registration (:func:`assertion_policy`);
- **one owner per ``pod:`` key** (`consent_key_owners`): a second subject for a
  key another subject holds here is refused; the owner is released when the last
  grant carrying the key ends (``db/key_ledger.py`` does that, in the flush);
- the holder's **suspension** of a key (`consent_key_suspensions`), which takes
  it out of the served set until a newer assertion lifts it.

Codes and hashes only. Nothing here stores a key in clear: owners and
suspensions are keyed by the blind index, and the ledger entries it writes seal
the key like every other entry.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from ds.governance import KEY_ASSERTION_METHODS
from ds.governance.dataplane import split_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..db.models import (
    DECISION_KEY_CAUSES,
    ConsentKeyAssertionORM,
    ConsentKeyEventORM,
    ConsentKeyOwnerORM,
    ConsentKeySuspensionORM,
    ConsentRequestORM,
)
from ..db.sealed import blind_index

#: The key type one subject holds at a time. A supply point has one customer of
#: record; other key types carry no such rule.
OWNED_KEY_TYPE = "pod"


# ── recipes ──────────────────────────────────────────────────────────────────


def canonical(value) -> str:
    """Sorted-keys, compact JSON — the one serialisation every digest here uses."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assertion_ref(assertion: dict | None) -> str | None:
    """``sha256_hex(canonical(assertion))`` — the assertion exactly as stored."""
    if not assertion:
        return None
    return sha256_hex(canonical(assertion))


def key_indexes(keys: Iterable[str]) -> list[str]:
    """The sorted, de-duplicated blind indexes of *keys*."""
    return sorted({blind_index(key) for key in keys})


def keys_digest(keys: Iterable[str] | None) -> str | None:
    """``sha256_hex("\\n".join(sorted(set(key_index))))``; ``None`` for no keys."""
    indexes = key_indexes(keys or ())
    if not indexes:
        return None
    return sha256_hex("\n".join(indexes))


def decision_ref(agreement_id: str, keys: Iterable[str]) -> str:
    """The release link a data-plane *allow* carries.

    ``sha256_hex(agreement_id + "\\n" + "\\n".join(sorted(set(key_index))))``
    over every key the allow serves. An allow serving no key hashes
    ``agreement_id + "\\n"``. The holder's ledger holds every ``key_index``, so an
    auditor recomputes it for a candidate key set without opening a key.
    """
    return sha256_hex(agreement_id + "\n" + "\n".join(key_indexes(keys)))


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes for a timezone column; they are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def parse_moment(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value)
    return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


# ── policy ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AssertionPolicy:
    required: bool
    methods: tuple[str, ...]
    #: Where the answer came from — the offer's declaration, or the default.
    source: str


def assertion_policy(
    offer, keys: Iterable[str] | None, *, dev: bool
) -> AssertionPolicy:
    """What this holder demands of a registration carrying *keys* under *offer*.

    The offer's ``key_assertion`` declaration decides when there is one. An
    offer that declares nothing requires an assertion for a ``pod:`` key outside
    ``DS_ENV=dev`` — a supply point identifies a household, and releasing its
    data on nobody's word is the case this exists to stop — and accepts every
    method. In dev, and for other key types, an undeclared offer does not
    require one; an assertion that is sent is still checked.
    """
    declared = getattr(offer, "key_assertion", None)
    if declared is not None:
        return AssertionPolicy(
            bool(declared.required), tuple(declared.methods), "offer"
        )
    has_pod = any(_type_of(key) == OWNED_KEY_TYPE for key in keys or ())
    return AssertionPolicy(
        has_pod and not dev,
        tuple(KEY_ASSERTION_METHODS),
        "default (pod: keys outside DS_ENV=dev)",
    )


def _type_of(key: str) -> str | None:
    try:
        return split_key(key)[0]
    except ValueError:
        return None


# ── the ledger, read as "is this key still carried by a grant" ───────────────


def carrying_consents(session: Session, key_index: str) -> set[str]:
    """The decisions whose last key event for *key_index* added it.

    Reads the key ledger, the one place the key can be compared (the rows hold
    it sealed). The holder's own suspend and lift entries are skipped: they say
    nothing about what a decision carries. Synchronous, so the flush listener can
    call it; an async caller goes through ``AsyncSession.run_sync``.
    """
    rows = session.execute(
        select(ConsentKeyEventORM.consent_id, ConsentKeyEventORM.event)
        .where(
            ConsentKeyEventORM.key_index == key_index,
            ConsentKeyEventORM.cause.in_(DECISION_KEY_CAUSES),
        )
        .order_by(ConsentKeyEventORM.at, ConsentKeyEventORM.id)
    ).all()
    last: dict[str | None, str] = {}
    for consent_id, event in rows:
        last[consent_id] = event
    return {cid for cid, event in last.items() if cid is not None and event == "added"}


def release_unless_carried(session: Session, key_indexes: Iterable[str]) -> None:
    """Release the owner of each key no grant carries any more. Never deletes."""
    now = datetime.now(UTC)
    for key_index in key_indexes:
        if carrying_consents(session, key_index):
            continue
        owners = session.execute(
            select(ConsentKeyOwnerORM).where(
                ConsentKeyOwnerORM.key_index == key_index,
                ConsentKeyOwnerORM.released_at.is_(None),
            )
        ).scalars()
        for owner in owners:
            owner.released_at = now


# ── claims ───────────────────────────────────────────────────────────────────


class KeyHeldElsewhere(Exception):
    """A ``pod:`` key another subject holds at this holder (→ 409).

    Carries the key's position in the call, never the key or the other subject.
    """

    def __init__(self, position: int) -> None:
        self.position = position
        super().__init__(
            f"key already held by another subject, or registered by another "
            f"organisation, at this holder (keys[{position}]); the collector that "
            "registered it withdraws it, or the holder suspends it, before it can "
            "be registered again"
        )


class KeySuspendedByHolder(Exception):
    """A suspended key, sent under an assertion no newer than the suspension (→ 409)."""

    def __init__(self, position: int, suspended_at: datetime) -> None:
        self.position = position
        self.suspended_at = suspended_at
        super().__init__(
            f"key suspended by the holder (keys[{position}]) since "
            f"{suspended_at.isoformat()}; only a key_assertion verified after "
            "that moment lifts it"
        )


@dataclass(frozen=True)
class LiftedSuspension:
    keys_digest: str
    subject_id: str
    assertion_ref: str


async def record_assertion(
    session: AsyncSession, assertion: dict, collector: str | None
) -> str:
    """Store *assertion* under its ref (once) and return the ref."""
    ref = assertion_ref(assertion)
    if await session.get(ConsentKeyAssertionORM, ref) is None:
        session.add(
            ConsentKeyAssertionORM(
                assertion_ref=ref,
                assertion=assertion,
                collector=collector,
                recorded_at=datetime.now(UTC),
            )
        )
    return ref


async def _active_suspension(
    session: AsyncSession, key_index: str
) -> ConsentKeySuspensionORM | None:
    return (
        await session.execute(
            select(ConsentKeySuspensionORM).where(
                ConsentKeySuspensionORM.key_index == key_index,
                ConsentKeySuspensionORM.lifted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _active_owner(
    session: AsyncSession, key_index: str
) -> ConsentKeyOwnerORM | None:
    return (
        await session.execute(
            select(ConsentKeyOwnerORM).where(
                ConsentKeyOwnerORM.key_index == key_index,
                ConsentKeyOwnerORM.released_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _ledger_entries_for_carriers(
    session: AsyncSession, key: str, key_index: str, *, event: str, cause: str
) -> int:
    """One holder entry per decision now carrying *key*; returns how many."""
    carriers = await session.run_sync(lambda s: carrying_consents(s, key_index))
    if not carriers:
        return 0
    rows = (
        await session.execute(
            select(ConsentRequestORM).where(ConsentRequestORM.id.in_(carriers))
        )
    ).scalars()
    now = datetime.now(UTC)
    batch = uuid.uuid4().hex[:12]
    count = 0
    for n, row in enumerate(sorted(rows, key=lambda r: r.id)):
        session.add(
            ConsentKeyEventORM(
                id=f"{now.strftime('%Y%m%dT%H%M%S%f')}-{n:04d}-{batch}",
                consent_id=row.id,
                offer_id=row.offer_id,
                dataset_id=row.dataset_id,
                consumer_id=row.consumer_id,
                key=key,
                event=event,
                cause=cause,
                decided_by=row.decided_by,
                collector=row.collector,
                at=now,
                assertion_ref=assertion_ref(
                    (row.legal_basis or {}).get("key_assertion")
                ),
            )
        )
        count += 1
    return count


async def claim_keys(
    session: AsyncSession,
    *,
    subject_id: str,
    keys: list[str],
    collector: str | None,
    assertion: dict | None,
) -> list[LiftedSuspension]:
    """Check and record that *subject_id* holds *keys* here, before the grant.

    Raises :class:`KeyHeldElsewhere` for a ``pod:`` key another subject holds,
    or this subject under another organisation's assertion,
    and :class:`KeySuspendedByHolder` for a suspended key whose assertion is not
    newer than the suspension. Otherwise records the owner (or refreshes its
    assertion) and lifts each suspension the newer assertion clears, returning
    them for the caller to put on the record once the transaction commits.
    """
    ref = assertion_ref(assertion)
    verified_at = parse_moment((assertion or {}).get("verified_at"))
    now = datetime.now(UTC)
    lifted: list[LiftedSuspension] = []
    for position, key in enumerate(keys):
        key_index = blind_index(key)
        suspension = await _active_suspension(session, key_index)
        if suspension is not None:
            suspended_at = _aware(suspension.suspended_at)
            if verified_at is None or verified_at <= suspended_at:
                raise KeySuspendedByHolder(position, suspended_at)
        if _type_of(key) == OWNED_KEY_TYPE:
            owner = await _active_owner(session, key_index)
            # The owner is a subject **and the organisation that asserted it**:
            # the same DID under another collector's assertion is refused too.
            # A DID can outlive a membership, and the responsibility for the
            # key is the asserting organisation's until its grant ends (ADR-0027).
            if owner is not None and (
                owner.subject_id != subject_id or owner.collector != collector
            ):
                raise KeyHeldElsewhere(position)
            if owner is None:
                session.add(
                    ConsentKeyOwnerORM(
                        key_index=key_index,
                        subject_id=subject_id,
                        collector=collector,
                        since=now,
                        assertion_ref=ref,
                    )
                )
            elif ref is not None:
                owner.assertion_ref = ref
        if suspension is not None:
            suspension.lifted_at = now
            suspension.lifted_by_assertion_ref = ref
            await _ledger_entries_for_carriers(
                session, key, key_index, event="added", cause="suspension_lifted"
            )
            lifted.append(
                LiftedSuspension(
                    keys_digest=sha256_hex(key_index),
                    subject_id=subject_id,
                    assertion_ref=ref or "",
                )
            )
    await session.flush()
    return lifted


# ── suspension ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Suspension:
    suspended_at: datetime
    reason: str
    grants_affected: int
    already_suspended: bool
    keys_digest: str
    subject_id: str | None


async def suspend_key(
    session: AsyncSession, *, key: str, reason: str, acted_by: dict | None
) -> Suspension:
    """Take *key* out of the served set; idempotent while it stays suspended."""
    key_index = blind_index(key)
    digest = sha256_hex(key_index)
    owner = await _active_owner(session, key_index)
    existing = await _active_suspension(session, key_index)
    if existing is not None:
        return Suspension(
            suspended_at=_aware(existing.suspended_at),
            reason=existing.reason,
            grants_affected=0,
            already_suspended=True,
            keys_digest=digest,
            subject_id=owner.subject_id if owner else None,
        )
    now = datetime.now(UTC)
    session.add(
        ConsentKeySuspensionORM(
            key_index=key_index, reason=reason, suspended_at=now, acted_by=acted_by
        )
    )
    affected = await _ledger_entries_for_carriers(
        session, key, key_index, event="removed", cause="holder_suspension"
    )
    await session.flush()
    return Suspension(
        suspended_at=now,
        reason=reason,
        grants_affected=affected,
        already_suspended=False,
        keys_digest=digest,
        subject_id=owner.subject_id if owner else None,
    )


async def suspended_key_indexes(session: AsyncSession) -> set[str]:
    """The blind indexes of every key the holder has suspended, now."""
    return set(
        (
            await session.execute(
                select(ConsentKeySuspensionORM.key_index).where(
                    ConsentKeySuspensionORM.lifted_at.is_(None)
                )
            )
        ).scalars()
    )
