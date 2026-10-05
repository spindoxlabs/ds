"""The key records outlive the decision row, and only the purge removes them (ADR-0027).

The ledger, the key owners, the assertions and the lifted suspensions are the
holder's evidence of what it released and on whose word. Erasing a decision row
leaves them (`ON DELETE SET NULL`, not `CASCADE`); nothing deletes them on a
schedule; `connector.db.retention.purge` removes what the retention period
(default ten years, GDPR Art. 17(3)(e)) has passed — and nothing younger, and
never a key a grant still carries.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import (
    ConsentKeyAssertionORM,
    ConsentKeyEventORM,
    ConsentKeyOwnerORM,
)
from connector.db.retention import purge
from connector.services import consent_service, key_records

DATASET = "datasets.silver.grid_meters"
OFFER = "test-meter-release"
A = "did:web:rec.example.org:users:ex-00001"
B = "did:web:rec.example.org:users:ex-00002"
KEY_A, KEY_B = "pod:EX000E00000001", "pod:EX000E00000002"
ASSERTION = {"terms": "rec-pod-assertion/1", "method": "uploaded-document"}


def test_the_ledger_no_longer_cascades_with_its_decision():
    fk = next(iter(ConsentKeyEventORM.__table__.c.consent_id.foreign_keys))
    assert fk.ondelete == "SET NULL"
    assert ConsentKeyEventORM.__table__.c.consent_id.nullable


async def _grant(session, subject, key, *, enabled=True):
    if enabled:
        await key_records.record_assertion(session, ASSERTION, None)
        await key_records.claim_keys(
            session, subject_id=subject, keys=[key], collector=None, assertion=ASSERTION
        )
    await consent_service.set_subject_data_sharing(
        session,
        subject_id=subject,
        dataset_id=DATASET,
        consumer_id=consent_service.WILDCARD_CONSUMER,
        enabled=enabled,
        purpose=["EnergyCommunityOperation"],
        recipient="grid-operator",
        recipient_role="metering",
        offer_id=OFFER,
        legal_basis={"key_assertion": ASSERTION} if enabled else None,
        keys=[key] if enabled else None,
    )


async def _age_everything(session, days: int) -> None:
    then = datetime.now(UTC) - timedelta(days=days)
    await session.execute(update(ConsentKeyEventORM).values(at=then))
    await session.execute(
        update(ConsentKeyOwnerORM)
        .where(ConsentKeyOwnerORM.released_at.is_not(None))
        .values(released_at=then)
    )
    await session.execute(update(ConsentKeyAssertionORM).values(recorded_at=then))


async def _count(session, model) -> int:
    return len(list((await session.execute(select(model))).scalars()))


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_the_purge_removes_only_what_the_period_has_passed(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await _grant(session, A, KEY_A)  # ends below
        await _grant(session, B, KEY_B)  # still carried
    async with factory() as session, session.begin():
        await _grant(session, A, KEY_A, enabled=False)

    async with factory() as session, session.begin():
        # Young: nothing goes, even with --apply.
        counts = await session.run_sync(
            lambda s: purge(s, retention_days=3650, apply=True)
        )
        assert set(counts.values()) == {0}

        await _age_everything(session, 4000)
        dry = await session.run_sync(lambda s: purge(s, retention_days=3650))
        assert dry["consent_key_events"] == 2  # KEY_A's grant and withdrawal
        assert dry["consent_key_owners"] == 1  # A's released ownership
        # B's carried key still references the shared assertion.
        assert dry["consent_key_assertions"] == 0
        # A dry run deletes nothing.
        assert await _count(session, ConsentKeyEventORM) == 3

        done = await session.run_sync(
            lambda s: purge(s, retention_days=3650, apply=True)
        )
        assert done == dry
        remaining = list((await session.execute(select(ConsentKeyEventORM))).scalars())
        assert [e.key for e in remaining] == [KEY_B]
        owners = list((await session.execute(select(ConsentKeyOwnerORM))).scalars())
        assert [(o.subject_id, o.released_at) for o in owners] == [(B, None)]


def test_a_retention_of_less_than_a_day_is_refused():
    with pytest.raises(ValueError):
        purge(None, retention_days=0)
