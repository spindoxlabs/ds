"""drop domain_events.processed

The column was written `True` unconditionally by the single writer
(`event_service.ingest_event`) and read by nothing, in this repository or any
other. It describes an asynchronous queue this service does not have: ingest is
synchronous and transactional, so a `domain_events` row exists precisely because
it was materialised, and there is no second state for it to be in.

Leaving it costs more than the byte: `NOT NULL` with a `False` default means the
next writer that forgets it records every event as unprocessed, which reads as a
backlog to anyone looking at the table.

The composite index this migration does *not* touch — `ix_domain_events_subject_occurred`
from `0002` — is now declared on the model too, so autogenerate stops proposing
to drop it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("domain_events", "processed")


def downgrade() -> None:
    op.add_column(
        "domain_events",
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
