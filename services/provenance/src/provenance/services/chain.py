"""The event record is append-only and hash-chained (`L-17`), and person ids age out (`L-18`).

Every `domain_events` row carries `seq`, `prev_hash` and `record_hash`:

    record_hash = sha256(prev_hash || "\\n" || canonical(row))

over one chain per store (a store is one participant's). Changing, removing or
reordering a row breaks every hash after it, and `verify` says where. Removing
the newest rows is visible only against a head recorded elsewhere, which is why
`verify` returns the head.

**The chain hashes a pseudonym of every person id, never the id itself.**
`canonical` replaces `subject_id`, `user_did` and `authorized_subject_ids` with
``pseud:<HMAC-SHA256(key, id)>`` before hashing. The retention job
(`apply_retention`) later writes that same pseudonym into the stored row, so a
pseudonymised row hashes exactly as it did on the day it was written and the
chain stays verifiable end to end. A row whose person id was replaced by anyone
else's pseudonym does not.

The key is `PROVENANCE_SUBJECT_PSEUDONYM_KEY`. Changing it changes every hash:
it is set once per store and never rotated.

The graph (`prov_nodes`, `prov_relations`) and `access_log` are projections of
this record and are not chained. The API cannot change or delete them either.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models import AccessLogORM, DomainEventORM, ProvNodeORM, ProvRelationORM

log = logging.getLogger(__name__)

GENESIS = "0" * 64
PSEUDONYM_PREFIX = "pseud:"

#: Payload fields that name a person. `acted_by.subject` is not one of them: it
#: names the operator or client that *decided* something (`L-5`), which stays
#: attributable for the life of the record.
PERSON_FIELDS = ("subject_id", "user_did")
PERSON_LIST_FIELDS = ("authorized_subject_ids",)
#: The same ids as an activity node's `external_meta` carries them.
NODE_META_FIELDS = ("subjectId",)
NODE_META_LIST_FIELDS = ("authorizedSubjectIds",)

#: Serialises appends on Postgres; SQLite serialises writers by itself.
_CHAIN_LOCK = 0x70726F76  # "prov"
_BATCH = 1000


def _key(key: str | None) -> bytes:
    return (key if key is not None else get_settings().subject_pseudonym_key).encode()


def pseudonym(value: str, key: str | None = None) -> str:
    """The stable pseudonym of a person id. A pseudonym maps to itself."""
    if value.startswith(PSEUDONYM_PREFIX):
        return value
    digest = hmac.new(_key(key), value.encode(), hashlib.sha256).hexdigest()
    return PSEUDONYM_PREFIX + digest


def _pseudonymise_fields(
    data: dict, scalars: tuple[str, ...], lists: tuple[str, ...], key: str | None
) -> dict:
    out = dict(data)
    for name in scalars:
        if isinstance(out.get(name), str):
            out[name] = pseudonym(out[name], key)
    for name in lists:
        if isinstance(out.get(name), list):
            out[name] = [pseudonym(v, key) if isinstance(v, str) else v for v in out[name]]
    return out


def pseudonymise_payload(payload: dict, key: str | None = None) -> dict:
    return _pseudonymise_fields(payload, PERSON_FIELDS, PERSON_LIST_FIELDS, key)


def person_ids(payload: dict) -> set[str]:
    """The clear-text person ids a payload still names."""
    found = {payload.get(name) for name in PERSON_FIELDS}
    for name in PERSON_LIST_FIELDS:
        found.update(payload.get(name) or [])
    return {v for v in found if isinstance(v, str) and not v.startswith(PSEUDONYM_PREFIX)}


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def canonical(row: DomainEventORM, key: str | None = None) -> str:
    """What a row's hash covers: every column but its own id and the server time."""
    record = {
        "seq": row.seq,
        "event_id": row.event_id,
        "event_type": row.event_type,
        "occurred_at": _utc(row.occurred_at),
        "payload": pseudonymise_payload(row.payload or {}, key),
        "prov_node_id": row.prov_node_id,
        "agreement_id": row.agreement_id,
        "data_product_id": row.data_product_id,
        "provider_did": row.provider_did,
        "consumer_did": row.consumer_did,
        "subject_id": pseudonym(row.subject_id, key) if row.subject_id else None,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(prev_hash: str, row: DomainEventORM, key: str | None = None) -> str:
    material = prev_hash + "\n" + canonical(row, key)
    return hashlib.sha256(material.encode()).hexdigest()


def link(row: DomainEventORM, seq: int, prev_hash: str, key: str | None = None) -> str:
    """Give `row` its place in the chain. Returns its hash, the next row's `prev_hash`."""
    row.seq = seq
    row.prev_hash = prev_hash
    row.record_hash = record_hash(prev_hash, row, key)
    return row.record_hash


async def _head(session: AsyncSession) -> tuple[int, str]:
    result = await session.execute(
        select(DomainEventORM.seq, DomainEventORM.record_hash)
        .where(DomainEventORM.seq.is_not(None))
        .order_by(DomainEventORM.seq.desc())
        .limit(1)
    )
    head = result.first()
    return (head[0], head[1]) if head else (0, GENESIS)


async def _lock(session: AsyncSession) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK})


async def append(session: AsyncSession, row: DomainEventORM) -> None:
    """Chain a new row onto the head. Holds the chain lock until the transaction ends."""
    await _lock(session)
    seq, prev = await _head(session)
    link(row, seq + 1, prev)


async def backfill(session: AsyncSession) -> int:
    """Chain every row that has no place yet, oldest first. Returns how many."""
    await _lock(session)
    seq, prev = await _head(session)
    rows = (
        await session.execute(
            select(DomainEventORM)
            .where(DomainEventORM.seq.is_(None))
            .order_by(DomainEventORM.received_at, DomainEventORM.id)
        )
    ).scalars()
    count = 0
    for row in rows:
        seq += 1
        prev = link(row, seq, prev)
        count += 1
    await session.flush()
    return count


@dataclass
class Verification:
    ok: bool = True
    records: int = 0
    head: str = GENESIS
    pseudonymised: int = 0
    unchained: int = 0
    first_failure: dict[str, Any] | None = None

    def fail(self, seq: int | None, reason: str) -> None:
        if self.first_failure is None:
            self.first_failure = {"seq": seq, "reason": reason}
        self.ok = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "records": self.records,
            "head": self.head,
            "pseudonymised": self.pseudonymised,
            "unchained": self.unchained,
            "firstFailure": self.first_failure,
        }


async def verify(session: AsyncSession) -> Verification:
    """Recompute the chain from the first row. Stops at nothing: counts everything."""
    out = Verification()
    expected_seq, prev = 1, GENESIS
    last_seq = 0
    while True:
        rows = (
            await session.execute(
                select(DomainEventORM)
                .where(DomainEventORM.seq > last_seq)
                .order_by(DomainEventORM.seq)
                .limit(_BATCH)
            )
        ).scalars().all()
        if not rows:
            break
        for row in rows:
            if row.seq != expected_seq:
                out.fail(row.seq, f"sequence gap: expected {expected_seq}")
            if row.prev_hash != prev:
                out.fail(row.seq, "prev_hash does not match the previous record")
            if record_hash(row.prev_hash or "", row) != row.record_hash:
                out.fail(row.seq, "record_hash does not match the record")
            if row.pseudonymised_at is not None:
                out.pseudonymised += 1
            out.records += 1
            prev = row.record_hash or ""
            last_seq = row.seq or 0  # never None: selected by `seq > last_seq`
            expected_seq = last_seq + 1
        session.expunge_all()
    out.head = prev
    out.unchained = (
        await session.scalar(
            select(func.count(DomainEventORM.id)).where(DomainEventORM.seq.is_(None))
        )
    ) or 0
    if out.unchained:
        out.fail(None, f"{out.unchained} record(s) not chained — run the backfill")
    return out


# ── Retention of person ids (`L-18`) ─────────────────────────────────────────


@dataclass
class RetentionResult:
    cutoff: str
    events: int = 0
    access_log: int = 0
    nodes: int = 0
    renamed_agents: int = 0
    ids: set[str] = field(default_factory=set, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cutoff": self.cutoff,
            "events": self.events,
            "accessLog": self.access_log,
            "nodes": self.nodes,
            "renamedAgents": self.renamed_agents,
        }


async def apply_retention(
    session: AsyncSession, days: int, now: datetime | None = None
) -> RetentionResult:
    """Replace the person ids of everything older than `days` with their pseudonyms.

    Nothing is deleted and no hash changes: the stored value becomes exactly
    what the chain already covers. An agent node named by a person id is renamed
    only once **no** newer record still names that id in clear, so the graph
    never holds the same person under two names at once.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    result = RetentionResult(cutoff=cutoff.isoformat())

    rows = (
        await session.execute(
            select(DomainEventORM).where(
                DomainEventORM.pseudonymised_at.is_(None),
                DomainEventORM.occurred_at < cutoff,
            )
        )
    ).scalars().all()
    node_ids: set[str] = set()
    for row in rows:
        result.ids |= person_ids(row.payload or {})
        if row.subject_id and not row.subject_id.startswith(PSEUDONYM_PREFIX):
            result.ids.add(row.subject_id)
        row.payload = pseudonymise_payload(row.payload or {})
        if row.subject_id:
            row.subject_id = pseudonym(row.subject_id)
        row.pseudonymised_at = now
        if row.prov_node_id:
            node_ids.add(row.prov_node_id)
        result.events += 1

    # The activity nodes those events materialised carry the same ids.
    if node_ids:
        nodes = (
            await session.execute(select(ProvNodeORM).where(ProvNodeORM.id.in_(node_ids)))
        ).scalars()
        for node in nodes:
            if node.external_meta:
                meta = _pseudonymise_fields(
                    node.external_meta, NODE_META_FIELDS, NODE_META_LIST_FIELDS, None
                )
                if meta != node.external_meta:
                    node.external_meta = meta
                    result.nodes += 1

    logs = (
        await session.execute(select(AccessLogORM).where(AccessLogORM.logged_at < cutoff))
    ).scalars()
    for entry in logs:
        if entry.subject_ids and any(
            isinstance(v, str) and not v.startswith(PSEUDONYM_PREFIX) for v in entry.subject_ids
        ):
            entry.subject_ids = [pseudonym(v) for v in entry.subject_ids]
            result.access_log += 1

    await session.flush()
    result.renamed_agents = await _rename_agents(session, result.ids)
    await session.flush()

    # The audit of the run itself: counts and the cutoff, never an id.
    log.info("person-id retention applied: %s", result.as_dict())
    return result


async def _still_named(session: AsyncSession) -> set[str]:
    """Every person id a record not yet past retention names in clear."""
    named: set[str] = set()
    rows = await session.execute(
        select(DomainEventORM.payload, DomainEventORM.subject_id).where(
            DomainEventORM.pseudonymised_at.is_(None)
        )
    )
    for payload, subject_id in rows:
        named |= person_ids(payload or {})
        if subject_id:
            named.add(subject_id)
    return named


async def _rename_agents(session: AsyncSession, ids: set[str]) -> int:
    if not ids:
        return 0
    retired = ids - await _still_named(session)
    renamed = 0
    for clear in sorted(retired):
        node = (
            await session.execute(select(ProvNodeORM).where(ProvNodeORM.iri == clear))
        ).scalar_one_or_none()
        if node is None:
            continue
        alias = pseudonym(clear)
        existing = (
            await session.execute(select(ProvNodeORM).where(ProvNodeORM.iri == alias))
        ).scalar_one_or_none()
        if existing is None:
            node.iri = alias
            node.label = alias
        else:
            await _merge_into(session, node, existing)
        renamed += 1
    return renamed


async def _merge_into(session: AsyncSession, old: ProvNodeORM, target: ProvNodeORM) -> None:
    """Move every edge of `old` onto `target`, then drop `old`.

    Reached when a person came back after an earlier run had already renamed
    them: the newer clear-text node joins the pseudonymous one.
    """
    edges = (
        await session.execute(
            select(ProvRelationORM).where(
                (ProvRelationORM.subject_id == old.id) | (ProvRelationORM.object_id == old.id)
            )
        )
    ).scalars().all()
    for edge in edges:
        subject = target.id if edge.subject_id == old.id else edge.subject_id
        obj = target.id if edge.object_id == old.id else edge.object_id
        duplicate = (
            await session.execute(
                select(ProvRelationORM.id).where(
                    ProvRelationORM.relation_type == edge.relation_type,
                    ProvRelationORM.subject_id == subject,
                    ProvRelationORM.object_id == obj,
                )
            )
        ).first()
        if duplicate:
            await session.delete(edge)
        else:
            edge.subject_id, edge.object_id = subject, obj
    await session.flush()
    await session.delete(old)
