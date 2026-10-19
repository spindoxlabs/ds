"""`upsert_agreement` — one row per agreement, whichever writer arrives first, or both.

The consumer's negotiation status route and the FINALIZED webhook both record the
agreement. They used to select, then insert: concurrent, both saw no row, the second
insert broke `agreement_id`'s unique key, the webhook answered 500 — losing the shared
DSP id only the webhook carries, so the EDR named the local id and the provider answered
`agreement_unknown` (2026-10-19, a driver polling the status route each second).

A real two-connection race needs Postgres; these pin the two halves of the fix instead:
the insert itself tolerates an existing row, and the webhook completes the row the
status route wrote.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ContractAgreementORM
from connector.services import agreement_service
from connector.services.agreement_service import upsert_agreement

LOCAL = "local-agreement-1"
SHARED = "dsp-agreement-1"


def _row(**extra):
    return {
        "agreement_id": LOCAL,
        "asset_id": "datasets.example",
        "consumer_id": "did:web:consumer.example.org",
        "provider_id": "did:web:provider.example.org",
        "policy_snapshot": {},
        "agreed_at": datetime.now(UTC),
        **extra,
    }


async def _rows(engine) -> list[ContractAgreementORM]:
    async with async_sessionmaker(engine)() as session:
        return list((await session.execute(select(ContractAgreementORM))).scalars())


@pytest.mark.rule("X-20")
@pytest.mark.asyncio
async def test_the_webhook_completes_the_row_the_status_route_wrote(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await upsert_agreement(session, **_row())  # the status route: no DSP id
    async with factory() as session, session.begin():
        await upsert_agreement(
            session,
            **_row(
                dsp_agreement_id=SHARED,
                consumer_organization_id="example-org",
                consumer_organization_type="rec",
            ),
        )
    (row,) = await _rows(engine)
    assert row.dsp_agreement_id == SHARED
    assert (row.consumer_organization_id, row.consumer_organization_type) == (
        "example-org",
        "rec",
    )


@pytest.mark.rule("X-20")
@pytest.mark.asyncio
async def test_a_late_writer_never_overwrites_what_the_webhook_stored(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await upsert_agreement(session, **_row(dsp_agreement_id=SHARED))
    async with factory() as session, session.begin():
        await upsert_agreement(session, **_row(dsp_agreement_id="other"))
    (row,) = await _rows(engine)
    assert row.dsp_agreement_id == SHARED


@pytest.mark.rule("X-20")
@pytest.mark.asyncio
async def test_the_insert_tolerates_a_row_that_already_exists(engine, monkeypatch):
    """The concurrent case: the row appears between nothing and the insert. Issued as
    `INSERT … ON CONFLICT (agreement_id) DO NOTHING`, so the second writer cannot fail
    on the unique key. *Red:* the select-then-insert this replaced."""
    seen: list[str] = []
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        execute = session.execute

        async def spy(statement, *args, **kwargs):
            if getattr(statement, "is_insert", False):
                seen.append(str(statement.compile(dialect=sqlite.dialect())))
            return await execute(statement, *args, **kwargs)

        monkeypatch.setattr(session, "execute", spy)
        await upsert_agreement(session, **_row())
        await upsert_agreement(session, **_row(dsp_agreement_id=SHARED))
    assert seen and all(
        "ON CONFLICT (agreement_id) DO NOTHING" in sql for sql in seen
    ), seen
    (row,) = await _rows(engine)
    assert row.dsp_agreement_id == SHARED


@pytest.mark.rule("X-20")
def test_postgres_spells_the_same_conflict():
    """Every deployment runs Postgres; this suite runs SQLite. The Postgres statement
    the same values produce carries the same clause."""
    statement = (
        agreement_service.postgresql_insert(ContractAgreementORM)
        .values(id="x", **_row())
        .on_conflict_do_nothing(index_elements=["agreement_id"])
    )
    assert "ON CONFLICT (agreement_id) DO NOTHING" in str(
        statement.compile(dialect=postgresql.dialect())
    )
