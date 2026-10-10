"""consent_collectors: who revoked, and the explicit reinstatement

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-10

A revoked collector pair stays revoked when it is added again (the anchor's
bootstrap re-adds it on every start). Lifting a revocation is its own operation,
`reinstate`, and the row records it: who, when, why. `revoked_by` completes the
revocation's own record. Rows written before this revision have none of the four.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_COLUMNS = ("revoked_by", "reinstated_at", "reinstated_by", "reinstatement_reason")


def upgrade() -> None:
    op.add_column(
        "consent_collectors", sa.Column("revoked_by", sa.Text(), nullable=True)
    )
    op.add_column(
        "consent_collectors",
        sa.Column("reinstated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consent_collectors", sa.Column("reinstated_by", sa.Text(), nullable=True)
    )
    op.add_column(
        "consent_collectors",
        sa.Column("reinstatement_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("consent_collectors", column)
