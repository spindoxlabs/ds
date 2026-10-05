"""The key records' retention, and the only path that deletes them (ADR-0027).

The key ledger (`consent_key_events`), the key owners (`consent_key_owners`), the
collectors' key assertions (`consent_key_assertions`) and the holder's lifted
suspensions (`consent_key_suspensions`) are the holder's evidence of what it
released, for whom, and on whose word. They are **not** deleted with a consent
row — erasing a decision nulls the ledger's reference to it and leaves the entry
— and nothing deletes them on a schedule. They are kept for
``CONNECTOR_KEY_RECORD_RETENTION_DAYS`` (default 3650: the Italian ordinary
limitation period, art. 2946 c.c., pending legal counsel) after the key stopped
being carried, on the basis of GDPR Art. 17(3)(e).

After that period an operator runs::

    python -m connector.db.retention purge            # dry run: counts only
    python -m connector.db.retention purge --apply    # deletes

What goes, each measured from the cutoff ``now - retention``:

- every ledger entry of a key **no grant carries any more** whose newest entry
  is older than the cutoff, and that no active suspension names;
- every owner row **released** before the cutoff;
- every suspension **lifted** before the cutoff;
- every assertion recorded before the cutoff that no remaining ledger entry or
  owner row references.

Nothing younger than the cutoff is touched, and an active owner or suspension
never is.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (
    DECISION_KEY_CAUSES,
    ConsentKeyAssertionORM,
    ConsentKeyEventORM,
    ConsentKeyOwnerORM,
    ConsentKeySuspensionORM,
)

log = logging.getLogger(__name__)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def purge(
    session: Session,
    *,
    retention_days: int,
    now: datetime | None = None,
    apply: bool = False,
) -> dict[str, int]:
    """Count — and with ``apply`` delete — what the retention period has passed.

    Synchronous: the CLI drives it through ``run_sync``, a test through the same.
    """
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)

    entries = session.execute(
        select(
            ConsentKeyEventORM.id,
            ConsentKeyEventORM.key_index,
            ConsentKeyEventORM.consent_id,
            ConsentKeyEventORM.event,
            ConsentKeyEventORM.cause,
            ConsentKeyEventORM.at,
        ).order_by(ConsentKeyEventORM.at, ConsentKeyEventORM.id)
    ).all()
    by_key: dict[str, list] = defaultdict(list)
    for entry in entries:
        by_key[entry.key_index].append(entry)
    suspended = set(
        session.execute(
            select(ConsentKeySuspensionORM.key_index).where(
                ConsentKeySuspensionORM.lifted_at.is_(None)
            )
        ).scalars()
    )

    ledger_ids: list[str] = []
    for key_index, rows in by_key.items():
        if key_index in suspended:
            continue
        last: dict[str | None, str] = {}
        for row in rows:
            if row.cause in DECISION_KEY_CAUSES:
                last[row.consent_id] = row.event
        carried = any(
            cid is not None and event == "added" for cid, event in last.items()
        )
        if carried or _aware(rows[-1].at) >= cutoff:
            continue
        ledger_ids.extend(row.id for row in rows)

    owner_ids = list(
        session.execute(
            select(ConsentKeyOwnerORM.id).where(
                ConsentKeyOwnerORM.released_at.is_not(None),
                ConsentKeyOwnerORM.released_at < cutoff,
            )
        ).scalars()
    )
    suspension_ids = list(
        session.execute(
            select(ConsentKeySuspensionORM.id).where(
                ConsentKeySuspensionORM.lifted_at.is_not(None),
                ConsentKeySuspensionORM.lifted_at < cutoff,
            )
        ).scalars()
    )

    gone_entries = set(ledger_ids)
    gone_owners = set(owner_ids)
    still_referenced = {
        ref
        for ref_id, ref in session.execute(
            select(ConsentKeyEventORM.id, ConsentKeyEventORM.assertion_ref)
        ).all()
        if ref and ref_id not in gone_entries
    } | {
        ref
        for ref_id, ref in session.execute(
            select(ConsentKeyOwnerORM.id, ConsentKeyOwnerORM.assertion_ref)
        ).all()
        if ref and ref_id not in gone_owners
    }
    assertion_refs = [
        ref
        for ref, recorded_at in session.execute(
            select(
                ConsentKeyAssertionORM.assertion_ref,
                ConsentKeyAssertionORM.recorded_at,
            )
        ).all()
        if _aware(recorded_at) < cutoff and ref not in still_referenced
    ]

    counts = {
        "consent_key_events": len(ledger_ids),
        "consent_key_owners": len(owner_ids),
        "consent_key_suspensions": len(suspension_ids),
        "consent_key_assertions": len(assertion_refs),
    }
    if apply:
        for model, column, ids in (
            (ConsentKeyEventORM, ConsentKeyEventORM.id, ledger_ids),
            (ConsentKeyOwnerORM, ConsentKeyOwnerORM.id, owner_ids),
            (ConsentKeySuspensionORM, ConsentKeySuspensionORM.id, suspension_ids),
            (
                ConsentKeyAssertionORM,
                ConsentKeyAssertionORM.assertion_ref,
                assertion_refs,
            ),
        ):
            for start in range(0, len(ids), 500):
                session.execute(
                    delete(model).where(column.in_(ids[start : start + 500]))
                )
    return counts


def _main() -> int:  # pragma: no cover - exercised through `purge`
    import argparse
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from ..config import get_settings

    parser = argparse.ArgumentParser(prog="python -m connector.db.retention")
    parser.add_argument("command", choices=["purge"])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete; without it the purge only counts what it would delete",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    async def run() -> dict[str, int]:
        engine = create_async_engine(settings.database_url)
        try:
            async with AsyncSession(engine) as session, session.begin():
                return await session.run_sync(
                    lambda s: purge(
                        s,
                        retention_days=settings.key_record_retention_days,
                        apply=args.apply,
                    )
                )
        finally:
            await engine.dispose()

    counts = asyncio.run(run())
    verb = "deleted" if args.apply else "would delete (dry run; --apply deletes)"
    for table, n in counts.items():
        log.info(
            "retention %d days: %s %d row(s) from %s",
            settings.key_record_retention_days,
            verb,
            n,
            table,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
