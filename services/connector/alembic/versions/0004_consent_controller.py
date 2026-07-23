"""consent rows carry a controller, a controller role and their sharing offer

The consent key becomes (subject, purpose, controller-role) rather than
(subject, purpose, organisation): a participant can act in several capacities,
and consent to one of them is not consent to another.

Existing rows keep NULL controller columns. They are not back-filled — there is
no honest value to invent for a row created before the vocabulary existed, and
for a consent-required dataset such a row now fails closed and surfaces in
/my-data as a one-time passive prompt.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consent_requests", sa.Column("controller", sa.Text(), nullable=True))
    op.add_column("consent_requests", sa.Column("controller_role", sa.Text(), nullable=True))
    op.add_column("consent_requests", sa.Column("offer_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("consent_requests", "offer_id")
    op.drop_column("consent_requests", "controller_role")
    op.drop_column("consent_requests", "controller")
