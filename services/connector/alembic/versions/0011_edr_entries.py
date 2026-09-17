"""the EDR is delivered to the connector and kept here

EDC 0.18.0's v5 management API has no EDR endpoint; the connector used to read
``/v3/edrs/{id}/dataaddress``. The EDR now arrives in the
``TransferProcessStarted`` event EDC posts to the transfer's callback address,
and ``edr_entries`` keeps it, one row per transfer. See
``EdrEntryORM`` for why the delivered data address is stored whole.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edr_entries",
        sa.Column("transfer_id", sa.Text(), primary_key=True),
        sa.Column("participant_context_id", sa.Text(), nullable=True),
        sa.Column("agreement_id", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("auth_type", sa.Text(), nullable=False, server_default="bearer"),
        sa.Column("authorization", sa.Text(), nullable=False),
        sa.Column("data_address", sa.JSON(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("edr_entries")
