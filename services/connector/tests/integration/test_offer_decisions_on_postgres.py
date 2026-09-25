"""`GET /consent/admin/decisions`'s store reads on the schema the migrations build.

The unit suite runs them on SQLite. Two things there differ on PostgreSQL and
decide who is listed: ``legal_basis`` is a ``json`` column, and "who collected
this cell" reads ``legal_basis ->> 'collector'`` beside the row's ``collector``;
and the page is a ``DISTINCT`` over subjects ordered and resumed by id. This
proves both after `alembic upgrade head`: an organisation's own cells only,
including a grant another organisation's relayed withdrawal rewrote; the
member's withdrawal presented; pages that cover every subject once.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    collected_decisions,
    collected_subjects_page,
    set_subject_data_sharing,
)

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]
GATED = "datasets.silver.meters"
OFFER = "test-flexibility"
OURS = "did:web:collector.example.org"
THEIRS = "did:web:second.example.org"
WHY = "Membership ended in example-rec"


def member(n: int) -> str:
    return f"did:web:collector.example.org:users:ex-{n:05d}"


async def _migrated(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=UNIT_DIR,
        env={**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def _decide(session, subject, *, by, enabled, decided_by, **extra):
    return await set_subject_data_sharing(
        session,
        subject_id=subject,
        dataset_id=GATED,
        consumer_id=WILDCARD_CONSUMER,
        enabled=enabled,
        purpose=["FlexibilityResearch"],
        recipient="example-org",
        offer_id=OFFER,
        legal_basis={"source": "community-portal", "collector": by},
        collector=by,
        decided_by=decided_by,
        **extra,
    )


@pytest.mark.rule("D-20")
async def test_an_organisation_s_own_cells_presented_and_paged_on_postgres(
    empty_database,
):
    await _migrated(empty_database)
    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    granted, both, relayed, theirs = member(1), member(2), member(3), member(4)
    try:
        async with factory() as session, session.begin():
            for subject in (granted, both, relayed):
                await _decide(
                    session, subject, by=OURS, enabled=True, decided_by="subject"
                )
            await _decide(
                session, theirs, by=THEIRS, enabled=True, decided_by="subject"
            )
        # The member withdraws, then we withdraw on our own: two rows.
        async with factory() as session, session.begin():
            members_row = await _decide(
                session, both, by=OURS, enabled=False, decided_by="subject"
            )
            members_row_id = members_row.id
        async with factory() as session, session.begin():
            await _decide(
                session,
                both,
                by=OURS,
                enabled=False,
                decided_by="collector",
                reason=WHY,
            )
        # Another organisation relays the member's withdrawal over our grant,
        # which rewrites the row's `collector`; the evidence still names us.
        async with factory() as session, session.begin():
            await _decide(
                session, relayed, by=THEIRS, enabled=False, decided_by="subject"
            )

        async with factory() as session:
            first, more = await collected_subjects_page(
                session,
                organisation=OURS,
                offer_id=OFFER,
                dataset_ids=[GATED],
                after=None,
                limit=2,
            )
            assert (first, more) == ([granted, both], True)
            rest, more = await collected_subjects_page(
                session,
                organisation=OURS,
                offer_id=OFFER,
                dataset_ids=[GATED],
                after=first[-1],
                limit=2,
            )
            assert (rest, more) == ([relayed], False)

            presented = await collected_decisions(
                session,
                organisation=OURS,
                offer_id=OFFER,
                dataset_ids=[GATED],
                subject_ids=[*first, *rest, theirs],
            )
        assert set(presented) == {(s, GATED) for s in (granted, both, relayed)}
        assert presented[(granted, GATED)].status == "granted"
        row = presented[(both, GATED)]
        assert (row.id, row.status, row.decided_by) == (
            members_row_id,
            "revoked",
            "subject",
        )
        row = presented[(relayed, GATED)]
        assert (row.status, row.decided_by, row.collector) == (
            "revoked",
            "subject",
            THEIRS,
        )
    finally:
        await engine.dispose()
