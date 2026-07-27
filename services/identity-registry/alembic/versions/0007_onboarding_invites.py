"""onboarding invites

An organisation applying to join has no identity yet, so the intake route cannot
be authenticated the usual way. A fully public write on the service holding every
private key is a spam and enumeration surface, so an operator-issued single-use
code gates it instead.

Codes are stored hashed: a leaked database should not yield usable invites, and
nothing reads them back — the code is shown once, when it is issued.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_invites",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        # Redeemed rather than deleted, so an operator can still see which
        # application a given invite produced.
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_id", sa.Text(), nullable=True),
        sa.UniqueConstraint("code_hash", name="uq_onboarding_invites_code_hash"),
    )
    op.create_index(
        "ix_onboarding_invites_code_hash", "onboarding_invites", ["code_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_invites_code_hash", table_name="onboarding_invites")
    op.drop_table("onboarding_invites")
