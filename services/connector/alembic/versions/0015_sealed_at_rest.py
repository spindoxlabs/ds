"""data keys and EDRs are sealed at rest

``consent_requests.subject_keys``, ``consent_key_events.key`` and the EDR
(``edr_entries.authorization``, ``edr_entries.data_address``) become ciphertext
(``connector.db.sealed``). ``consent_key_events.key_index`` is the keyed blind
index that keeps equality lookups on a key possible.

**Backfill.** Every existing value is sealed with the first key of
``CONNECTOR_AT_REST_KEYS`` and every key event indexed with
``CONNECTOR_KEY_INDEX_SECRET``, so both must be set to the deployment's own
values before this runs: a backfill under the dev keys has to be resealed.

**Downgrade** opens every value again with the configured keys.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from ds_auth.production import is_production

from alembic import op
from connector.config import DEV_AT_REST_KEY, DEV_KEY_INDEX_SECRET, get_settings
from connector.db.sealed import PREFIX, parse_keys, seal_rows, sealer

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

#: The JSON columns that become text. `seal_rows` then seals their serialisation.
_JSON_COLUMNS = (("consent_requests", "subject_keys"), ("edr_entries", "data_address"))


def _to_text(table: str, column: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN "{column}" TYPE TEXT '
            f'USING "{column}"::text'
        )
    else:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=sa.Text())


def upgrade() -> None:
    settings = get_settings()
    if is_production() and (
        DEV_AT_REST_KEY in parse_keys(settings.at_rest_keys)
        or settings.key_index_secret == DEV_KEY_INDEX_SECRET
    ):
        # Sealing a deployment's rows under the committed dev keys would encrypt
        # them with keys anyone can read; refuse before anything is written.
        raise RuntimeError(
            "CONNECTOR_AT_REST_KEYS / CONNECTOR_KEY_INDEX_SECRET hold the dev "
            "values; set this deployment's own before migrating"
        )
    bind = op.get_bind()
    for table, column in _JSON_COLUMNS:
        _to_text(table, column)
    # JSON `null` stored as a value is not a set of keys either.
    op.execute(
        "UPDATE consent_requests SET subject_keys = NULL WHERE subject_keys = 'null'"
    )
    op.add_column(
        "consent_key_events", sa.Column("key_index", sa.String(64), nullable=True)
    )
    seal_rows(bind, sealer(), plaintext_ok=True)
    with op.batch_alter_table("consent_key_events") as batch:
        batch.alter_column("key_index", existing_type=sa.String(64), nullable=False)
    op.create_index(
        "ix_consent_key_events_key_index", "consent_key_events", ["key_index"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    s = sealer()
    for table, pk, column in (
        ("consent_requests", "id", "subject_keys"),
        ("consent_key_events", "id", "key"),
        ("edr_entries", "transfer_id", "authorization"),
        ("edr_entries", "transfer_id", "data_address"),
    ):
        rows = bind.execute(
            sa.text(
                f'SELECT {pk}, "{column}" FROM {table} WHERE "{column}" IS NOT NULL'
            )
        ).all()
        for row_id, stored in rows:
            if str(stored).startswith(PREFIX):
                bind.execute(
                    sa.text(f'UPDATE {table} SET "{column}" = :v WHERE {pk} = :id'),
                    {"v": s.open(str(stored)), "id": row_id},
                )
    op.drop_index("ix_consent_key_events_key_index", table_name="consent_key_events")
    with op.batch_alter_table("consent_key_events") as batch:
        batch.drop_column("key_index")
    if bind.dialect.name == "postgresql":
        for table, column in _JSON_COLUMNS:
            op.execute(
                f'ALTER TABLE {table} ALTER COLUMN "{column}" TYPE JSON '
                f'USING "{column}"::json'
            )
    else:
        for table, column in _JSON_COLUMNS:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(column, type_=sa.JSON())
