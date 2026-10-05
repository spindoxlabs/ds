"""hash-chain the event record; mark pseudonymised rows

`domain_events` becomes an append-only hash chain (rulebook `L-17`,
`services/chain.py`): `seq`, `prev_hash`, `record_hash`. `pseudonymised_at`
records when retention replaced a row's person ids with their pseudonyms
(`L-18`).

**Backfill.** Every existing row is chained here, oldest first by
`received_at`, under `PROVENANCE_SUBJECT_PSEUDONYM_KEY` — so the migration must
run with the key the service will run with. A row the chain covers from this
point on was not tamper-evident before it, and nothing here can say whether it
was changed earlier. `provenance-admin backfill` chains any row this missed.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""
from __future__ import annotations

from types import SimpleNamespace

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_COLUMNS = (
    "id",
    "event_id",
    "event_type",
    "occurred_at",
    "payload",
    "prov_node_id",
    "agreement_id",
    "data_product_id",
    "provider_did",
    "consumer_did",
    "subject_id",
)


def upgrade() -> None:
    op.add_column("domain_events", sa.Column("seq", sa.BigInteger(), nullable=True))
    op.add_column("domain_events", sa.Column("prev_hash", sa.String(64), nullable=True))
    op.add_column("domain_events", sa.Column("record_hash", sa.String(64), nullable=True))
    op.add_column(
        "domain_events",
        sa.Column("pseudonymised_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_domain_events_seq", "domain_events", ["seq"])
    _backfill()


def _backfill() -> None:
    # Imported here: the hash is the service's, and must be computed exactly as
    # `verify` will recompute it.
    from provenance.services.chain import GENESIS, link

    bind = op.get_bind()
    table = sa.table(
        "domain_events",
        *(
            sa.column(name, sa.JSON()) if name == "payload" else sa.column(name)
            for name in _COLUMNS
        ),
        sa.column("received_at"),
        sa.column("seq"),
        sa.column("prev_hash"),
        sa.column("record_hash"),
    )
    rows = bind.execute(
        sa.select(*(table.c[name] for name in _COLUMNS)).order_by(
            table.c.received_at, table.c.id
        )
    ).mappings()
    prev = GENESIS
    for seq, row in enumerate(list(rows), start=1):
        record = SimpleNamespace(**row)
        prev = link(record, seq, prev)
        bind.execute(
            table.update()
            .where(table.c.id == record.id)
            .values(seq=record.seq, prev_hash=record.prev_hash, record_hash=record.record_hash)
        )


def downgrade() -> None:
    op.drop_constraint("uq_domain_events_seq", "domain_events", type_="unique")
    op.drop_column("domain_events", "pseudonymised_at")
    op.drop_column("domain_events", "record_hash")
    op.drop_column("domain_events", "prev_hash")
    op.drop_column("domain_events", "seq")
