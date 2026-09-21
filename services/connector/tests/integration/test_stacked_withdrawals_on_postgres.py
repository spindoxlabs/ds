"""ADR-0020 on the schema the migrations build: each withdrawal is its own record.

The unit suite proves the writer on SQLite. This proves, on PostgreSQL after
`alembic upgrade head`, that a member's withdrawal over a collector's is a second
row — the collector's `decided_by`, `collector`, `revoked_at` and
`revocation_reason` untouched — and that the member's row is the one every
"latest" reader orders first, with `timestamptz` and the `ck_consent_decided_by`
constraint in play. No migration is needed for it; this is the evidence.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from connector.db.models import ConsentRequestORM
from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    _latest_decision_first,
    check_consent_detail,
    get_latest_offer_consent,
    set_subject_data_sharing,
)

pytestmark = pytest.mark.integration

UNIT_DIR = Path(__file__).resolve().parents[2]
GATED = "datasets.silver.meters"
COLLECTOR = "did:web:collector.example.org"
SUBJECT = "did:web:collector.example.org:users:member-001"
WHY = "Membership ended in example-rec"


async def _migrated(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=UNIT_DIR,
        env={**os.environ, "CONNECTOR_DATABASE_URL": database_url, "DS_ENV": "dev"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def _decide(session, *, enabled: bool, decided_by: str, **extra):
    return await set_subject_data_sharing(
        session,
        subject_id=SUBJECT,
        dataset_id=GATED,
        consumer_id=WILDCARD_CONSUMER,
        enabled=enabled,
        purpose=["FlexibilityResearch"],
        recipient="example-org",
        offer_id="test-flexibility",
        collector=COLLECTOR,
        decided_by=decided_by,
        **extra,
    )


@pytest.mark.rule("D-15c", "D-12a")
async def test_a_member_s_withdrawal_over_a_collector_s_is_a_second_row(
    empty_database,
):
    await _migrated(empty_database)
    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _rows() -> list[ConsentRequestORM]:
        async with factory() as session:
            result = await session.execute(
                select(ConsentRequestORM)
                .where(ConsentRequestORM.subject_id == SUBJECT)
                .order_by(*_latest_decision_first())
            )
            return list(result.scalars())

    try:
        async with factory() as session, session.begin():
            await _decide(session, enabled=True, decided_by="subject")
        async with factory() as session, session.begin():
            await _decide(session, enabled=False, decided_by="collector", reason=WHY)
        [collector_row] = await _rows()
        before = (
            collector_row.id,
            collector_row.decided_by,
            collector_row.collector,
            collector_row.revoked_at,
            collector_row.revocation_reason,
        )

        async with factory() as session, session.begin():
            await _decide(session, enabled=False, decided_by="subject")

        rows = await _rows()
        assert len(rows) == 2
        member_row, collector_row = rows
        assert (
            collector_row.id,
            collector_row.decided_by,
            collector_row.collector,
            collector_row.revoked_at,
            collector_row.revocation_reason,
        ) == before
        assert before[1:3] == ("collector", COLLECTOR)
        assert before[4] == WHY
        assert (member_row.status, member_row.decided_by) == ("revoked", "subject")
        assert member_row.revoked_at >= collector_row.revoked_at
        assert member_row.revocation_reason != WHY

        async with factory() as session:
            allowed, _reason, deciding = await check_consent_detail(
                session,
                SUBJECT,
                GATED,
                "did:web:consumer.example.org",
                purpose=["FlexibilityResearch"],
                offer_id="test-flexibility",
            )
        assert not allowed
        assert deciding is not None and deciding.id == member_row.id
    finally:
        await engine.dispose()


@pytest.mark.rule("D-15c", "D-12a")
async def test_the_member_first_then_a_collector_two_rows_and_the_member_s_presented(
    empty_database,
):
    """The other order (the maintainer, 2026-09-21: "prioritize the member if
    both"): the collector's withdrawal is stored with its reason, and the
    member's own standing withdrawal is what the latest-row readers return."""
    await _migrated(empty_database)
    engine = create_async_engine(empty_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await _decide(session, enabled=True, decided_by="subject")
        async with factory() as session, session.begin():
            member = await _decide(session, enabled=False, decided_by="subject")
            member_id = member.id
        async with factory() as session, session.begin():
            ended = await _decide(
                session, enabled=False, decided_by="collector", reason=WHY
            )
            collector_id = ended.id
        assert collector_id != member_id

        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ConsentRequestORM).where(
                            ConsentRequestORM.subject_id == SUBJECT
                        )
                    )
                )
                .scalars()
                .all()
            )
            by = {row.id: row for row in rows}
            assert set(by) == {member_id, collector_id}
            assert by[collector_id].decided_by == "collector"
            assert by[collector_id].revocation_reason == WHY
            assert by[member_id].decided_by == "subject"

            latest = await get_latest_offer_consent(
                session, SUBJECT, GATED, WILDCARD_CONSUMER, "test-flexibility"
            )
            allowed, _reason, deciding = await check_consent_detail(
                session,
                SUBJECT,
                GATED,
                "did:web:consumer.example.org",
                purpose=["FlexibilityResearch"],
                offer_id="test-flexibility",
            )
        assert latest is not None and latest.id == member_id
        assert not allowed
        assert deciding is not None and deciding.id == member_id
    finally:
        await engine.dispose()
