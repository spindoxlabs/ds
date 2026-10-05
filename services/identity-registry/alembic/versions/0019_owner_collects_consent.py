"""Owner.collects_consent — the declared flag behind the collector client

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-05

ADR-0026. An organisation declared to collect its members' consent gets a
collector client (`svc-ds-collector-<alias>`) at promotion. Declared by the anchor
operator in `owners.yaml`, never inferred: existing owners default to `false`.
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "owners",
        sa.Column(
            "collects_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("owners", "collects_consent")
