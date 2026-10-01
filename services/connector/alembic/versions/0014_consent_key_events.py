"""the holder's key ledger

ADR-0022. ``consent_key_events`` records every key a granted decision started or
stopped carrying, so the holder can read the history of the keys its data plane
filters on. The consent rows cannot answer it: a withdrawal drops their keys and
a new registration replaces them.

**Backfill.** Each row that is granted and carries keys when this runs gets one
``added`` entry per key, cause ``backfill``, at its ``decided_at`` (or
``requested_at`` when it was never decided). Withdrawals made before this
revision cannot be recovered: those rows no longer hold the keys they carried.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-01
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

EVENTS = ("added", "removed")
CAUSES = ("grant", "withdrawal", "key_change", "backfill")


def upgrade() -> None:
    op.create_table(
        "consent_key_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "consent_id",
            sa.String(),
            sa.ForeignKey("consent_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("offer_id", sa.Text(), nullable=True),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("collector", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event IN ({})".format(", ".join(f"'{e}'" for e in EVENTS)),
            name="ck_consent_key_event",
        ),
        sa.CheckConstraint(
            "cause IN ({})".format(", ".join(f"'{c}'" for c in CAUSES)),
            name="ck_consent_key_event_cause",
        ),
    )
    op.create_index(
        "ix_consent_key_events_offer_at", "consent_key_events", ["offer_id", "at"]
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, offer_id, dataset_id, consumer_id, subject_keys, "
            "decided_by, collector, COALESCE(decided_at, requested_at) AS at "
            "FROM consent_requests "
            "WHERE status = 'granted' AND subject_keys IS NOT NULL"
        )
    ).mappings()
    table = sa.table(
        "consent_key_events",
        *(
            sa.column(name)
            for name in (
                "id",
                "consent_id",
                "offer_id",
                "dataset_id",
                "consumer_id",
                "key",
                "event",
                "cause",
                "decided_by",
                "collector",
                "at",
            )
        ),
    )
    entries = []
    for row in rows:
        keys = row["subject_keys"]
        if isinstance(keys, str):
            keys = json.loads(keys)
        at = row["at"]
        if isinstance(at, str):
            # SQLite returns the COALESCE as text.
            at = datetime.fromisoformat(at)
        batch = uuid.uuid4().hex[:12]
        for n, key in enumerate(sorted(set(keys or []))):
            entries.append(
                {
                    # Sorts in write order within one timestamp, as the
                    # listener's ids do (`db/key_ledger.py`, `_entry_id`).
                    "id": f"{at.strftime('%Y%m%dT%H%M%S%f')}-{n:04d}-{batch}",
                    "consent_id": row["id"],
                    "offer_id": row["offer_id"],
                    "dataset_id": row["dataset_id"],
                    "consumer_id": row["consumer_id"],
                    "key": key,
                    "event": "added",
                    "cause": "backfill",
                    "decided_by": row["decided_by"],
                    "collector": row["collector"],
                    "at": row["at"],
                }
            )
    if entries:
        op.bulk_insert(table, entries)


def downgrade() -> None:
    op.drop_index("ix_consent_key_events_offer_at", table_name="consent_key_events")
    op.drop_table("consent_key_events")
