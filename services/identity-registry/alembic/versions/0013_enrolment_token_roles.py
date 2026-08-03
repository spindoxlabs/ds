"""An enrolment token carries the roles and scopes it admits

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-03

`participant add` took `--roles` and `--scope` from whoever ran it. Enrolment
replaced that call, and the roles had nowhere to go: `enrol()` created a
`Participant` with an empty role list, so an enrolled provider was a participant
that could negotiate nothing.

They belong on the **token**, not on the request, and that is a governance
statement rather than a convenience. A candidate applies stating its intended
role (`DSSC-BIZ-136`); the authority decides whether to grant it. Letting the
enrolling party name its own roles would let a consumer enrol as a provider by
editing one field of a request it composes itself.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column("enrolment_tokens", sa.Column("roles", JSON_TYPE, nullable=True))
    op.add_column(
        "enrolment_tokens", sa.Column("allowed_scopes", JSON_TYPE, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("enrolment_tokens", "allowed_scopes")
    op.drop_column("enrolment_tokens", "roles")
