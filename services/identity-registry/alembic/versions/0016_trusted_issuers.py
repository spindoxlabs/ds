"""The dataspace's list of accredited entities

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-03

`DSSC-TRF-05` (a listing of trust anchors and trust service providers,
**including revoked ones** — *must*), `-07` (machine-readable), `-17` (a list of
accredited entities) and `DSSC-BIZ-143` (the Data Space Registry lists the trust
anchors onboarding is verified against).

Published at `GET /trust`, public and unauthenticated for the same reason the
revocation list is: a counterparty deciding whether to accept a credential must
be able to read it **before** it has any relationship with this dataspace. It is
also the first thing another dataspace initiative reads about us.

Seeded with this deployment's own trust anchor at `ir-cli bootstrap`.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "trusted_issuers",
        sa.Column("did", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("scope_of_attestation", JSON_TYPE, nullable=False),
        sa.Column("derives_authority_from", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("added_by", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("trusted_issuers")
