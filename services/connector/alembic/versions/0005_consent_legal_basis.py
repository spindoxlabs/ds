"""consent rows carry a legal-basis evidence record

Block B. A consent row now records *under what basis* it was written: the DPV
basis IRI, the consent-text version and locale, the SHA-256 of the rendered
text actually shown, the user-visible-facts hash, and the submission reference.
Codes and hashes only — never PII, so the connector DB stays out of the
personal-data business (§3.3).

Existing rows keep NULL. There is no basis to invent for a row created before
the evidence shape existed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consent_requests", sa.Column("legal_basis", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("consent_requests", "legal_basis")
