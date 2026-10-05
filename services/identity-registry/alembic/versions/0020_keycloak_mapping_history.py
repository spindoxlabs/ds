"""keycloak_mappings.released_at — a login moves to a new DID, the old row stays

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-05

ADR-0028. A person released by one organisation and joining another is issued a
new DID, and the collector's sync moves their login to it. The row it leaves is
history (`released_at` set), so (realm, user id) is unique among the rows not
released, not over the table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_OLD = "uq_keycloak_mappings_realm_user"
_NEW = "uq_keycloak_mappings_realm_user_current"


def upgrade() -> None:
    op.add_column(
        "keycloak_mappings",
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(_OLD, "keycloak_mappings", type_="unique")
    op.create_index(
        _NEW,
        "keycloak_mappings",
        ["keycloak_realm", "keycloak_user_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    # Refuses, through the constraint, while a login has history rows: which
    # DID it answers to then is an operator's decision, as in 0010.
    op.drop_index(_NEW, table_name="keycloak_mappings")
    op.create_unique_constraint(
        _OLD, "keycloak_mappings", ["keycloak_realm", "keycloak_user_id"]
    )
    op.drop_column("keycloak_mappings", "released_at")
