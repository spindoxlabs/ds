"""Compliance audit log routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db
from ...db.models import AccessLogORM
from ...schemas.audit import AccessLogEntry, AccessLogRead, AccessLogSummary

router = APIRouter()


@router.post("/audit/log", status_code=201, response_model=AccessLogRead)
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
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AccessLogORM)
    if consumer_id:
        stmt = stmt.where(AccessLogORM.consumer_id == consumer_id)
    if dataset_id:
        stmt = stmt.where(AccessLogORM.dataset_id == dataset_id)
    if agreement_id:
        stmt = stmt.where(AccessLogORM.agreement_id == agreement_id)
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
