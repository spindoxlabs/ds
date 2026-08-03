"""Normalise JSON `'null'` to SQL NULL in keys.private_jwk

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-03

`0012` made `keys.private_jwk` nullable so that an enrolled participant's
**public** key could be recorded here with no private half. It worked, and the
column still tested as NOT NULL: SQLAlchemy's JSON types store Python `None` as
the JSON value `'null'` unless `none_as_null=True` is set, so every enrolled
participant's row held `'null'::jsonb` and `private_jwk IS NULL` was False.

The consequence is the one the guard exists to prevent: `get_participant_key`
checks `private_jwk is None` before signing, and the check passed — so a request
to sign as a participant this instance cannot sign for would have reached
`decrypt_private_jwk` with a JSON null instead of being refused with a message
naming the right instance.

**SQLite deserialises `'null'` to `None`**, so the unit suite agreed with the
code while Postgres did not. The type is fixed in `db/models.py`; this migration
repairs the rows already written.
"""
import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        sa.text("UPDATE keys SET private_jwk = NULL WHERE private_jwk = 'null'::jsonb")
    )


def downgrade() -> None:
    # Nothing to undo: SQL NULL is what the column always meant. Writing
    # `'null'::jsonb` back would restore a bug, not a state.
    pass
