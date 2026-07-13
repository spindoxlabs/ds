"""add consumer access requests

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consumer_access_requests",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("counter_party_address", sa.Text(), nullable=False),
        sa.Column("offer_id", sa.Text(), nullable=False),
        sa.Column("assigner", sa.Text(), nullable=False),
        sa.Column("negotiation_id", sa.Text(), nullable=True),
        sa.Column("transfer_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("negotiation_id"),
    )


def downgrade() -> None:
    op.drop_table("consumer_access_requests")
