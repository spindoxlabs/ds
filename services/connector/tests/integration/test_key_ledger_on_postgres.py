"""The holder's key ledger on the schema the migrations build (ADR-0022).

The unit suite proves the listener on SQLite with `create_all`. Three things only
Postgres and the migration can show:

- **the backfill** — `0014` seeds one `added` entry per key of each decision that
  is granted with keys when it runs, and nothing for a withdrawn or keyless one;
- **the listener on Postgres** — a withdrawal through the service appends its
  `removed` entry in the same transaction;
- **the constraints** — the event and cause vocabularies are enforced, and
  deleting a decision row deletes its history (`ON DELETE CASCADE`), which is how
  erasure reaches the ledger.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    set_subject_data_sharing,
)

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]
DATASET = "datasets.silver.grid_meters"
OFFER = "test-meter-release"
COLLECTOR = "did:web:collector.example.org"


def _alembic_upgrade(database_url: str, target: str = "head"):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=UNIT_DIR,
        env={**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"},
        capture_output=True,
        text=True,
    )


async def _events(engine) -> list[tuple]:
    async with engine.connect() as conn:
        return [
            tuple(row)
            for row in await conn.execute(
                sa.text(
                    "SELECT consent_id, key, event, cause FROM consent_key_events "
                    "ORDER BY at, id"
                )
            )
        ]


async def test_0014_backfills_the_keys_granted_decisions_carry(empty_database):
    assert _alembic_upgrade(empty_database, "0013").returncode == 0
    engine = create_async_engine(empty_database)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO consent_requests "
                    "(id, subject_id, consumer_id, dataset_id, offer_id, status, "
                    " decided_by, collector, subject_keys, decided_at, "
                    " notification_sent) VALUES "
                    "('g1', 'did:web:x:users:a', '*', :ds, :offer, 'granted', "
                    "  'subject', :coll, '[\"pod:EX01\", \"pod:EX02\"]', "
                    "  '2026-09-01T10:00:00Z', false),"
                    "('g2', 'did:web:x:users:b', '*', :ds, :offer, 'granted', "
                    "  'subject', :coll, NULL, '2026-09-02T10:00:00Z', false),"
                    "('w1', 'did:web:x:users:c', '*', :ds, :offer, 'revoked', "
                    "  'subject', :coll, NULL, '2026-09-03T10:00:00Z', false)"
                ),
                {"ds": DATASET, "offer": OFFER, "coll": COLLECTOR},
            )

        result = _alembic_upgrade(empty_database)
        assert result.returncode == 0, result.stderr

        assert await _events(engine) == [
            ("g1", "pod:EX01", "added", "backfill"),
            ("g1", "pod:EX02", "added", "backfill"),
        ]
        async with engine.connect() as conn:
            at = (
                await conn.execute(
                    sa.text("SELECT DISTINCT at FROM consent_key_events")
                )
            ).scalar_one()
        assert at.isoformat().startswith("2026-09-01T10:00:00")
    finally:
        await engine.dispose()


async def test_the_listener_appends_in_the_decision_s_transaction(empty_database):
    assert _alembic_upgrade(empty_database).returncode == 0
    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def decide(enabled: bool, keys=None):
        async with factory() as session, session.begin():
            return await set_subject_data_sharing(
                session,
                subject_id="did:web:x:users:a",
                dataset_id=DATASET,
                consumer_id=WILDCARD_CONSUMER,
                enabled=enabled,
                purpose=["EnergyCommunityOperation"],
                recipient="grid-operator",
                recipient_role="metering",
                offer_id=OFFER,
                legal_basis={"source": "community-portal", "collector": COLLECTOR},
                collector=COLLECTOR,
                decided_by="subject",
                keys=keys,
            )

    try:
        row = await decide(True, keys=["pod:EX01"])
        await decide(False)
        assert await _events(engine) == [
            (row.id, "pod:EX01", "added", "grant"),
            (row.id, "pod:EX01", "removed", "withdrawal"),
        ]

        # The vocabularies are constraints, not conventions.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text(
                        "INSERT INTO consent_key_events (id, consent_id, dataset_id, "
                        "consumer_id, key, event, cause, at) VALUES "
                        "('x', :row, :ds, '*', 'pod:EX01', 'forgotten', 'grant', "
                        "now())"
                    ),
                    {"row": row.id, "ds": DATASET},
                )

        # Erasing the decision erases its history.
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("DELETE FROM consent_requests WHERE id = :row"),
                {"row": row.id},
            )
        assert await _events(engine) == []
    finally:
        await engine.dispose()
