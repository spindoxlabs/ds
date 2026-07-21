"""Domain event ingest and query routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, require_write_scope, get_settings_dep
from ...db.models import DomainEventORM
from ...schemas.context import JSONLDResponse
from ...schemas.events import DomainEvent, EventIngestResponse
from ...services.event_service import ingest_event

router = APIRouter()


@router.post("/events", response_model=EventIngestResponse, dependencies=[Depends(require_write_scope)])
async def ingest(
    event: DomainEvent,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    async with db.begin():
        result = await ingest_event(db, event)
    response.status_code = 200 if result.status == "duplicate" else 201
    return result


@router.get("/events")
async def list_events(
    event_type: str | None = None,
    agreement_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    stmt = select(DomainEventORM)
    if event_type:
        stmt = stmt.where(DomainEventORM.event_type == event_type)
    if agreement_id:
        stmt = stmt.where(DomainEventORM.agreement_id == agreement_id)
    stmt = stmt.order_by(DomainEventORM.occurred_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    events = result.scalars().all()

    graph = [
        {
            "@id": f"urn:event:{e.id}",
            "@type": f"ds:{e.event_type}",
            "ds:occurredAt": e.occurred_at.isoformat(),
            "ds:agreementId": e.agreement_id,
            "ds:dataProductId": e.data_product_id,
            "ds:providerDid": e.provider_did,
            "ds:consumerDid": e.consumer_did,
        }
        for e in events
    ]
    return JSONLDResponse(graph, settings.context_url)
