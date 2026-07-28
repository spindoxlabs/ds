"""a keycloak mapping records the username, not only the email

A dataspace decision names subjects by DID. Systems outside the dataspace name
the same people their own way: the REC registry resolves a member with
``Member.user_id == user.get_username()`` — Keycloak's ``preferred_username``.
Without that value stored, a consent decision about "these subjects" cannot be
turned into a query anywhere else, and the alternative — sending the DID, or the
email — is either meaningless to the receiver or PII on the wire.

Nullable and unbackfilled. ``email`` remains the fallback: this realm sets
username = email, and rows written before this column existed carry only the
email. Guessing a username from anything else would be worse than failing,
because a wrong one resolves to a different person's data.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("keycloak_mappings", sa.Column("username", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("keycloak_mappings", "username")
