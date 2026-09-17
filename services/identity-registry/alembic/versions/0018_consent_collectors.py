"""Consent collectors — an organisation a holder accepts consent registrations from

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-17

Plan `a-collector-registers-consent-at-the-holder`. A person consents where they
are a member (their community); the organisation holding their data (a grid
operator) registers that consent on its own connector. The holder accepts such
registrations only from the organisations listed here, for their own members.

A relation between two DIDs, marked revoked rather than deleted: consent rows
name the collector that registered them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_collectors",
        sa.Column("holder_did", sa.Text(), primary_key=True),
        sa.Column("collector_did", sa.Text(), primary_key=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("added_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("consent_collectors")
