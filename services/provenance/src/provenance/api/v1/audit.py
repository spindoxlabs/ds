"""Compliance audit log routes.

`access_log` records one dataspace-originated query each. It is written from the
`QueryExecuted` domain event (`services/event_service._record_access_log`) as
well as directly through `POST /audit/log`, so a deployment whose data plane
already reports queries to the connector's PEP route gets the compliance log
without wiring a second caller.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, require_write_scope
from ...db.models import AccessLogORM
from ...schemas.audit import AccessLogEntry, AccessLogRead, AccessLogSummary

router = APIRouter()

MAX_LIMIT = 500


def _mentions_subject(db: AsyncSession, subject_id: str):
    """`access_log.subject_ids` is a JSON array, so membership is dialect-specific.

    Postgres stores JSONB and answers with `@>`; SQLite stores JSON text and needs
    `json_each`. Both deployments matter — Postgres in production, SQLite under
    test — which is the same split `alembic/versions/0002` already carries.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return AccessLogORM.subject_ids.contains([subject_id])
    each = func.json_each(AccessLogORM.subject_ids).table_valued("value")
    return select(1).select_from(each).where(each.c.value == subject_id).exists()


@router.post(
    "/audit/log",
    status_code=201,
    response_model=AccessLogRead,
    dependencies=[Depends(require_write_scope)],
)
async def write_log_entry(
    entry: AccessLogEntry,
    db: AsyncSession = Depends(get_db),
):
    orm = AccessLogORM(**entry.model_dump())
    async with db.begin():
        db.add(orm)
    await db.refresh(orm)
    return orm


@router.get("/audit/log", response_model=list[AccessLogRead])
async def query_log(
    consumer_id: str | None = None,
    dataset_id: str | None = None,
    agreement_id: str | None = None,
    subject_id: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AccessLogORM)
    if consumer_id:
        stmt = stmt.where(AccessLogORM.consumer_id == consumer_id)
    if dataset_id:
        stmt = stmt.where(AccessLogORM.dataset_id == dataset_id)
    if agreement_id:
        stmt = stmt.where(AccessLogORM.agreement_id == agreement_id)
    # Declared since the route was written and never applied, so "show me every
    # query that touched this person's rows" — the one question the parameter
    # exists to answer — returned the whole log instead of that person's slice.
    if subject_id:
        stmt = stmt.where(_mentions_subject(db, subject_id))
    if from_:
        stmt = stmt.where(AccessLogORM.logged_at >= from_)
    if until:
        stmt = stmt.where(AccessLogORM.logged_at <= until)
    stmt = stmt.order_by(AccessLogORM.logged_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/audit/log/summary", response_model=AccessLogSummary)
async def log_summary(
    dataset_id: str,
    from_: datetime | None = Query(default=None, alias="from"),
    until: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AccessLogORM).where(AccessLogORM.dataset_id == dataset_id)
    if from_:
        stmt = stmt.where(AccessLogORM.logged_at >= from_)
    if until:
        stmt = stmt.where(AccessLogORM.logged_at <= until)
    result = await db.execute(stmt)
    entries = list(result.scalars().all())

    by_consumer: dict[str, int] = {}
    by_day: dict[str, int] = {}
    subjects: set[str] = set()

    for e in entries:
        by_consumer[e.consumer_id] = by_consumer.get(e.consumer_id, 0) + 1
        day = e.logged_at.date().isoformat()
        by_day[day] = by_day.get(day, 0) + 1
        if e.subject_ids:
            subjects.update(e.subject_ids)

    return AccessLogSummary(
        dataset_id=dataset_id,
        from_=from_,
        until=until,
        total_queries=len(entries),
        unique_consumers=len(by_consumer),
        unique_subjects=len(subjects),
        queries_by_consumer=by_consumer,
        queries_by_day=by_day,
    )
