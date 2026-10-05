"""Migration `0004` chains the rows already in a store, on a real Postgres (`L-17`).

The unit suite builds its schema with `create_all` on SQLite, so neither the
backfill nor the advisory lock `chain.append` takes on Postgres runs there.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from provenance.schemas.events import ConsentGranted
from provenance.services import chain
from provenance.services.event_service import ingest_event

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]
SUBJECT = "did:web:rec.example.org:users:ex-00001"


def _alembic(database_url: str, target: str) -> None:
    env = {**os.environ, "PROVENANCE_DATABASE_URL": database_url, "DS_ENV": "dev"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=UNIT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.rule("L-17")
async def test_existing_rows_are_chained_by_the_migration(empty_database: str) -> None:
    _alembic(empty_database, "0003")

    dsn = empty_database.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for n in range(3):
            payload = {
                "event_type": "ConsentGranted",
                "event_id": f"legacy-{n}",
                "occurred_at": (base + timedelta(hours=n)).isoformat(),
                "subject_id": SUBJECT,
                "dataset_id": "meters",
            }
            await conn.execute(
                "INSERT INTO domain_events (id, event_type, event_id, occurred_at,"
                " received_at, payload, subject_id)"
                " VALUES ($1, 'ConsentGranted', $2, $3, $4, $5::jsonb, $6)",
                f"row-{n}",
                f"legacy-{n}",
                base + timedelta(hours=n),
                base + timedelta(hours=n, minutes=1),
                json.dumps(payload),
                SUBJECT,
            )
    finally:
        await conn.close()

    _alembic(empty_database, "head")

    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await chain.verify(session)
        assert result.ok, result.as_dict()
        assert result.records == 3

        # A new event lands on the backfilled head, through the Postgres lock.
        async with factory() as session:
            await ingest_event(
                session,
                ConsentGranted(
                    event_id="new-1",
                    occurred_at=datetime.now(timezone.utc),
                    subject_id=SUBJECT,
                    dataset_id="meters",
                ),
            )
            await session.commit()
        async with factory() as session:
            await chain.apply_retention(session, days=30)
            await session.commit()
        async with factory() as session:
            result = await chain.verify(session)
        assert result.ok, result.as_dict()
        assert result.records == 4
        assert result.pseudonymised == 3
    finally:
        await engine.dispose()
