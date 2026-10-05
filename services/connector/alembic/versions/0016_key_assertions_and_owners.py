"""key assertions, one owner per key, holder suspensions; the ledger outlives a row

ADR-0027.

- ``consent_key_assertions``: a collector's assertion that the keys it
  registered are its member's, by its SHA-256 (``assertion_ref``).
- ``consent_key_owners``: which subject holds a ``pod:`` key here. **One active
  owner per key** — a partial unique index on ``key_index`` where
  ``released_at`` is null. Released rows are kept for the retention period.
- ``consent_key_suspensions``: the holder's suspensions of a key, at most one
  active per key.
- ``consent_key_events`` gains ``assertion_ref`` and two causes
  (``holder_suspension``, ``suspension_lifted``), and its reference to the
  decision row becomes nullable with ``ON DELETE SET NULL``: erasing a decision
  no longer erases its key history (it was ``ON DELETE CASCADE``).

**Backfill.** Each ``pod:`` key the ledger shows as carried by a grant gets one
active owner — the subject of the decisions carrying it, since the earliest
``added`` among them. **A key carried by two subjects' grants stops the
migration** with the number of such keys: which one holds it is a fact only the
collectors can establish, so the operator resolves it (one collector withdraws)
before migrating. Nothing is guessed. The ledger holds every key sealed and
indexed (``0015``), so the backfill reads only ``key_index`` and opens a key
only to read its type.

**Downgrade** drops the three tables and ``assertion_ref``; it deletes the
ledger entries whose decision row is gone (the old schema cannot hold them) and
the entries with the two new causes, then restores ``NOT NULL`` and the cascade.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

OLD_CAUSES = ("grant", "withdrawal", "key_change", "backfill")
NEW_CAUSES = OLD_CAUSES + ("holder_suspension", "suspension_lifted")

#: Lets batch mode name the foreign key 0014 created without a name (SQLite).
_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _fk_name() -> str:
    if op.get_bind().dialect.name == "postgresql":
        return "consent_key_events_consent_id_fkey"
    return "fk_consent_key_events_consent_id_consent_requests"


def _causes_check(causes: tuple[str, ...]) -> str:
    return "cause IN ({})".format(", ".join(f"'{c}'" for c in causes))


def _rewire_ledger(*, nullable: bool, ondelete: str, causes: tuple[str, ...]) -> None:
    with op.batch_alter_table(
        "consent_key_events", naming_convention=_NAMING, recreate="auto"
    ) as batch:
        batch.drop_constraint(_fk_name(), type_="foreignkey")
        batch.drop_constraint("ck_consent_key_event_cause", type_="check")
        batch.alter_column("consent_id", existing_type=sa.String(), nullable=nullable)
        batch.create_foreign_key(
            _fk_name(),
            "consent_requests",
            ["consent_id"],
            ["id"],
            ondelete=ondelete,
        )
        batch.create_check_constraint(
            "ck_consent_key_event_cause", _causes_check(causes)
        )


def upgrade() -> None:
    op.add_column(
        "consent_key_events", sa.Column("assertion_ref", sa.String(64), nullable=True)
    )
    _rewire_ledger(nullable=True, ondelete="SET NULL", causes=NEW_CAUSES)

    op.create_table(
        "consent_key_assertions",
        sa.Column("assertion_ref", sa.String(64), primary_key=True),
        sa.Column("assertion", sa.JSON(), nullable=False),
        sa.Column("collector", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "consent_key_owners",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key_index", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("collector", sa.Text(), nullable=True),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assertion_ref", sa.String(64), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_consent_key_owners_key_index", "consent_key_owners", ["key_index"]
    )
    op.create_index(
        "ux_consent_key_owners_active",
        "consent_key_owners",
        ["key_index"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
        sqlite_where=sa.text("released_at IS NULL"),
    )
    op.create_table(
        "consent_key_suspensions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key_index", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acted_by", sa.JSON(), nullable=True),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifted_by_assertion_ref", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "reason IN ('holder_change')", name="ck_consent_key_suspension_reason"
        ),
    )
    op.create_index(
        "ix_consent_key_suspensions_key_index",
        "consent_key_suspensions",
        ["key_index"],
    )
    op.create_index(
        "ux_consent_key_suspensions_active",
        "consent_key_suspensions",
        ["key_index"],
        unique=True,
        postgresql_where=sa.text("lifted_at IS NULL"),
        sqlite_where=sa.text("lifted_at IS NULL"),
    )
    _backfill_owners()


def _as_moment(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _backfill_owners() -> None:
    from connector.db.sealed import sealer

    bind = op.get_bind()
    entries = bind.execute(
        sa.text(
            "SELECT e.key_index, e.key, e.consent_id, e.event, e.at, "
            "c.subject_id, c.collector, c.status "
            "FROM consent_key_events e "
            "JOIN consent_requests c ON c.id = e.consent_id "
            "ORDER BY e.at, e.id"
        )
    ).mappings()
    s = sealer()
    last: dict[tuple[str, str], dict] = {}
    first_added: dict[tuple[str, str], datetime] = {}
    is_pod: dict[str, bool] = {}
    for entry in entries:
        index = entry["key_index"]
        if index not in is_pod:
            is_pod[index] = s.open(str(entry["key"])).startswith("pod:")
        cell = (index, entry["consent_id"])
        last[cell] = dict(entry)
        if entry["event"] == "added":
            first_added.setdefault(cell, _as_moment(entry["at"]))

    holders: dict[str, dict[str, dict]] = defaultdict(dict)
    for (index, consent_id), entry in last.items():
        if not is_pod.get(index) or entry["event"] != "added":
            continue
        if entry["status"] != "granted":
            continue
        since = first_added[(index, consent_id)]
        current = holders[index].get(entry["subject_id"])
        if current is None or since < current["since"]:
            holders[index][entry["subject_id"]] = {
                "since": since,
                "collector": entry["collector"],
            }

    conflicts = [index for index, by_subject in holders.items() if len(by_subject) > 1]
    if conflicts:
        raise RuntimeError(
            f"{len(conflicts)} pod: key(s) are carried by the grants of more than one "
            "subject at this holder. Which subject holds each is for the collectors "
            "to establish: have the collector withdraw the wrong registration "
            "(POST /consent/admin/shares, enabled=false), then migrate again "
            "(ADR-0027)."
        )

    import uuid

    table = sa.table(
        "consent_key_owners",
        *(
            sa.column(name)
            for name in ("id", "key_index", "subject_id", "collector", "since")
        ),
    )
    rows = [
        {
            "id": str(uuid.uuid4()),
            "key_index": index,
            "subject_id": subject_id,
            "collector": holder["collector"],
            "since": holder["since"],
        }
        for index, by_subject in sorted(holders.items())
        for subject_id, holder in by_subject.items()
    ]
    if rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_index("ux_consent_key_suspensions_active", "consent_key_suspensions")
    op.drop_index("ix_consent_key_suspensions_key_index", "consent_key_suspensions")
    op.drop_table("consent_key_suspensions")
    op.drop_index("ux_consent_key_owners_active", "consent_key_owners")
    op.drop_index("ix_consent_key_owners_key_index", "consent_key_owners")
    op.drop_table("consent_key_owners")
    op.drop_table("consent_key_assertions")
    op.execute(
        "DELETE FROM consent_key_events WHERE consent_id IS NULL "
        "OR cause IN ('holder_suspension', 'suspension_lifted')"
    )
    _rewire_ledger(nullable=False, ondelete="CASCADE", causes=OLD_CAUSES)
    with op.batch_alter_table("consent_key_events") as batch:
        batch.drop_column("assertion_ref")
