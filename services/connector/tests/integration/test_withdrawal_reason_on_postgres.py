"""`D-12a` on the schema the migrations build.

A collector's withdrawal may say why (`POST /consent/admin/shares`, `reason`).
The unit suite proves the route and runs on SQLite; this proves the cause lands
in `revocation_reason` — and not in `message`, which every read projects — on
PostgreSQL, through both withdrawal branches the writer has: mutating a standing
grant, and appending a refusal where nothing was granted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.api.v1.consent import REASON_MAX_LENGTH
from connector.db.models import ConsentRequestORM
from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    set_subject_data_sharing,
)

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]
GATED = "datasets.silver.meters"

COLLECTOR = "did:web:collector.example.org"
WHY = "Membership ended in example-rec" + "." * (REASON_MAX_LENGTH - 31)


async def _migrated(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=UNIT_DIR,
        env={**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def _decide(session, subject: str, *, enabled: bool, **extra):
    return await set_subject_data_sharing(
        session,
        subject_id=subject,
        dataset_id=GATED,
        consumer_id=WILDCARD_CONSUMER,
        enabled=enabled,
        purpose=["FlexibilityResearch"],
        recipient="example-org",
        offer_id="test-flexibility",
        collector=COLLECTOR,
        **extra,
    )


@pytest.mark.rule("D-12a")
@pytest.mark.parametrize("granted_first", [True, False], ids=["over-a-grant", "fresh"])
async def test_a_collector_s_reason_is_stored_where_no_read_projects_it(
    empty_database, granted_first
):
    assert len(WHY) == REASON_MAX_LENGTH
    subject = "did:web:collector.example.org:users:member-001"
    await _migrated(empty_database)
    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if granted_first:
            async with factory() as session, session.begin():
                await _decide(session, subject, enabled=True, decided_by="subject")
        async with factory() as session, session.begin():
            await _decide(
                session, subject, enabled=False, decided_by="collector", reason=WHY
            )

        async with factory() as session:
            [row] = (
                (
                    await session.execute(
                        select(ConsentRequestORM).where(
                            ConsentRequestORM.subject_id == subject
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert row.status == "revoked"
        assert row.decided_by == "collector"
        assert row.revocation_reason == WHY
        assert row.message != WHY
    finally:
        await engine.dispose()
