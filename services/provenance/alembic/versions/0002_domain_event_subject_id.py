"""index domain events by subject

A data subject reading their own history is the one query that must be scoped by
subject, and `subject_id` lived only inside the JSON payload while every other
filter dimension (agreement, data product, provider, consumer) was already a
column. Filtering a person's own view by scanning JSON is both slower and easier
to get subtly wrong.

Backfills from the payload so events recorded before this migration are visible
in that view — otherwise a subject's history would silently start today.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domain_events", sa.Column("subject_id", sa.Text(), nullable=True))

    # JSON extraction differs by dialect; both deployments matter (Postgres in
    # production, SQLite under test).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE domain_events
               SET subject_id = payload ->> 'subject_id'
             WHERE payload ? 'subject_id'
            """
        )
    else:
        op.execute(
            """
            UPDATE domain_events
               SET subject_id = json_extract(payload, '$.subject_id')
             WHERE json_extract(payload, '$.subject_id') IS NOT NULL
            """
        )

    op.create_index(
        "ix_domain_events_subject_id", "domain_events", ["subject_id"]
    )
    # The subject view is always "my events, newest first".
    op.create_index(
        "ix_domain_events_subject_occurred",
        "domain_events",
        ["subject_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_domain_events_subject_occurred", table_name="domain_events")
    op.drop_index("ix_domain_events_subject_id", table_name="domain_events")
    op.drop_column("domain_events", "subject_id")
