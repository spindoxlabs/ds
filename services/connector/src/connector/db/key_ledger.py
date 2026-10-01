"""The key ledger's writer: every change to the keys a granted decision carries.

ADR-0022. A holder's data plane serves the keys on its granted consent rows
(`subject_key_match`), and the rows forget: a withdrawal sets `subject_keys` to
null, and a new registration replaces them in place. So the history is appended
to `consent_key_events` as the rows change.

**A flush listener, not a call in each write path.** There are four paths that
move a row's keys today — the standing decision's grant, key update and
withdrawal in `set_subject_data_sharing`, and the subject's own approve and
revoke by id — and a fifth would have to remember a call it could not see. The
listener sees every one, in the same flush and so the same transaction as the
row: the ledger cannot say something the rows do not.

What a row *carries* is its keys while it is granted, and nothing otherwise. One
row's change is the difference between what it carried before the flush and
what it carries after, so:

- a new granted row with keys adds them (`grant`);
- a granted row becoming revoked removes what it carried (`withdrawal`);
- a granted row whose keys are replaced adds and removes the difference
  (`key_change`);
- a pending, rejected or keyless row adds nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .models import ConsentKeyEventORM, ConsentRequestORM


def _carried(status: str | None, keys: list | None) -> set[str]:
    return set(keys or []) if status == "granted" else set()


def _before(row: ConsentRequestORM) -> tuple[str | None, list | None]:
    """The row's status and keys as the database last saw them."""
    state = inspect(row)
    if state.transient or state.pending:
        return None, None

    def old(name: str):
        history = state.attrs[name].history
        if history.deleted:
            return history.deleted[0]
        return getattr(row, name)

    return old("status"), old("subject_keys")


def _entry_id(at: datetime, n: int, batch: str) -> str:
    """An id that sorts in write order within one timestamp.

    The history is read ordered by ``(at, id)``, and one key change writes its
    removals and additions at the same instant; a random id would order them
    by chance. So: the moment, the position in this row's batch, and a random
    tail that keeps ids unique across rows written in the same microsecond.
    """
    return f"{at.strftime('%Y%m%dT%H%M%S%f')}-{n:04d}-{batch}"


def entries_for(
    row: ConsentRequestORM,
    before_status: str | None,
    before_keys: list | None,
    *,
    now: datetime | None = None,
) -> list[ConsentKeyEventORM]:
    """The ledger entries one row's change produces.

    Side-effect free apart from giving a new row its id, so it is testable
    without a session.
    """
    was = _carried(before_status, before_keys)
    is_ = _carried(row.status, row.subject_keys)
    if was == is_:
        return []
    now = now or datetime.now(UTC)
    if before_status == "granted" and row.status != "granted":
        cause, at = "withdrawal", row.revoked_at or now
    elif before_status != "granted" and row.status == "granted":
        cause, at = "grant", row.decided_at or now
    else:
        cause, at = "key_change", now
    # A key change is the re-sender's act, not the granter's (`key_change_by`).
    decided_by = (
        row.key_change_by or row.decided_by if cause == "key_change" else row.decided_by
    )

    if row.id is None:
        # The primary key's default is applied at insert, after this listener.
        row.id = str(uuid.uuid4())

    batch = uuid.uuid4().hex[:12]
    order = iter(range(10_000))

    def entry(key: str, kind: str) -> ConsentKeyEventORM:
        return ConsentKeyEventORM(
            id=_entry_id(at, next(order), batch),
            consent_id=row.id,
            decision=row,
            offer_id=row.offer_id,
            dataset_id=row.dataset_id,
            consumer_id=row.consumer_id,
            key=key,
            event=kind,
            cause=cause,
            decided_by=decided_by,
            collector=row.collector,
            at=at,
        )

    return [entry(k, "removed") for k in sorted(was - is_)] + [
        entry(k, "added") for k in sorted(is_ - was)
    ]


@event.listens_for(Session, "before_flush")
def _record_key_changes(session: Session, _flush_context, _instances) -> None:
    for row in list(session.new) + list(session.dirty):
        if not isinstance(row, ConsentRequestORM):
            continue
        before_status, before_keys = _before(row)
        for entry in entries_for(row, before_status, before_keys):
            session.add(entry)
        row.key_change_by = None
