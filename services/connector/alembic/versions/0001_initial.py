"""initial connector schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_agreements",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("agreement_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("agreement_id"),
    )
    op.create_table(
        "consent_requests",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("purpose", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("notification_sent", sa.Boolean(), nullable=False),
        sa.Column("notification_url", sa.Text(), nullable=True),
        sa.Column("transfer_ids", sa.JSON(), nullable=True),
    )
    op.create_table(
        "consumer_transfers",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("transfer_id", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("contract_agreement_id", sa.Text(), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("transfer_id"),
    )


def downgrade() -> None:
    op.drop_table("consumer_transfers")
    op.drop_table("consent_requests")
    op.drop_table("contract_agreements")
