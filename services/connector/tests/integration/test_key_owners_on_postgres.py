"""Migration 0016 on Postgres: owners backfilled, one active owner per key (ADR-0027).

- **the backfill** — one active owner per `pod:` key a grant carries when the
  migration runs, and none for a released or non-`pod:` key;
- **the refusal** — a key two subjects' grants carry stops the migration, since
  which of them holds it is the collectors' fact, not the migration's guess;
- **the partial unique index** — a second active owner is refused by the
  database too, a released one is not;
- **down and up again** — the downgrade restores the 0015 shape.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
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
COLLECTOR = "did:web:rec.example.org"
A = "did:web:rec.example.org:users:ex-00001"
B = "did:web:rec.example.org:users:ex-00002"


def _alembic(database_url: str, *args: str):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=UNIT_DIR,
        env={**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"},
        capture_output=True,
        text=True,
    )


async def _grant(engine, subject: str, keys: list[str], *, enabled=True):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        return await set_subject_data_sharing(
            session,
            subject_id=subject,
            dataset_id=DATASET,
            consumer_id=WILDCARD_CONSUMER,
            enabled=enabled,
            purpose=["EnergyCommunityOperation"],
            recipient="grid-operator",
            recipient_role="metering",
            offer_id=OFFER,
            legal_basis={"source": "community-portal"},
            collector=COLLECTOR,
            decided_by="subject",
            keys=keys if enabled else None,
        )


async def _owners(engine) -> list[tuple]:
    async with engine.connect() as conn:
        return [
            tuple(row)
            for row in await conn.execute(
                sa.text(
                    "SELECT subject_id, released_at IS NULL FROM consent_key_owners "
                    "ORDER BY subject_id"
                )
            )
        ]


async def _drop_0016_tables(engine) -> None:
    """Stand at 0015 with rows the ORM (at head) wrote: drop what 0016 adds."""
    async with engine.begin() as conn:
        for table in (
            "consent_key_owners",
            "consent_key_suspensions",
            "consent_key_assertions",
        ):
            await conn.execute(sa.text(f"DELETE FROM {table}"))


async def test_0016_backfills_one_owner_per_carried_pod_key(empty_database):
    assert _alembic(empty_database, "upgrade", "head").returncode == 0
    engine = create_async_engine(empty_database)
    try:
        await _grant(engine, A, ["pod:EX01", "meter:M1"])
        await _grant(engine, B, ["pod:EX02"])
        await _grant(engine, B, [], enabled=False)  # B's key released
        await _drop_0016_tables(engine)

        down = _alembic(empty_database, "downgrade", "0015")
        assert down.returncode == 0, down.stderr
        up = _alembic(empty_database, "upgrade", "head")
        assert up.returncode == 0, up.stderr

        # A's pod: key only — not the meter: key, and not B's released one.
        assert await _owners(engine) == [(A, True)]
    finally:
        await engine.dispose()


async def test_0016_refuses_a_key_two_subjects_carry(empty_database):
    assert _alembic(empty_database, "upgrade", "0015").returncode == 0
    from connector.db.sealed import sealer

    s = sealer()
    engine = create_async_engine(empty_database)
    try:
        async with engine.begin() as conn:
            for n, subject in enumerate((A, B)):
                await conn.execute(
                    sa.text(
                        "INSERT INTO consent_requests (id, subject_id, consumer_id, "
                        "dataset_id, offer_id, status, decided_by, decided_at, "
                        "notification_sent) VALUES (:id, :subject, '*', :ds, :offer, "
                        "'granted', 'subject', now(), false)"
                    ),
                    {"id": f"g{n}", "subject": subject, "ds": DATASET, "offer": OFFER},
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO consent_key_events (id, consent_id, dataset_id, "
                        "consumer_id, key, key_index, event, cause, at) VALUES "
                        "(:id, :cid, :ds, '*', :key, :ix, 'added', 'grant', now())"
                    ),
                    {
                        "id": f"e{n}",
                        "cid": f"g{n}",
                        "ds": DATASET,
                        "key": s.seal("pod:EX01"),
                        "ix": s.index("pod:EX01"),
                    },
                )
        result = _alembic(empty_database, "upgrade", "head")
        assert result.returncode != 0
        assert "more than one subject" in result.stderr
    finally:
        await engine.dispose()


async def test_one_active_owner_per_key_is_a_database_rule(empty_database):
    assert _alembic(empty_database, "upgrade", "head").returncode == 0
    engine = create_async_engine(empty_database)
    insert = sa.text(
        "INSERT INTO consent_key_owners (id, key_index, subject_id, since, "
        "released_at) VALUES (:id, 'ix', :subject, now(), :released)"
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(insert, {"id": "o1", "subject": A, "released": None})
            # A released owner of the same key is history, not a conflict.
            await conn.execute(
                insert,
                {
                    "id": "o0",
                    "subject": B,
                    "released": datetime(2026, 1, 1, tzinfo=UTC),
                },
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(insert, {"id": "o2", "subject": B, "released": None})
        # The two new ledger causes are part of the vocabulary now.
        row = await _grant(engine, A, ["pod:EX09"])
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO consent_key_events (id, consent_id, dataset_id, "
                    "consumer_id, key, key_index, event, cause, at) VALUES "
                    "('s1', :row, :ds, '*', 'x', 'ix9', 'removed', "
                    "'holder_suspension', now())"
                ),
                {"row": row.id, "ds": DATASET},
            )
    finally:
        await engine.dispose()
