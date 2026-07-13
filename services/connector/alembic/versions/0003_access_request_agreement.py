"""link consumer access requests to contract agreements

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consumer_access_requests",
        sa.Column("contract_agreement_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("consumer_access_requests", "contract_agreement_id")
