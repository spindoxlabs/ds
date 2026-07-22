"""Convert participants.role (String) to participants.roles (JSONB array).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "participants",
        "role",
        new_column_name="roles",
        type_=postgresql.JSONB,
        postgresql_using="jsonb_build_array(role)",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "participants",
        "roles",
        new_column_name="role",
        type_=sa.String(16),
        postgresql_using="roles->>0",
        nullable=False,
    )
