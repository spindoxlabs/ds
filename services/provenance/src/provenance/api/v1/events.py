"""Domain event ingest and query routes."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import DomainEventORM
from ...dependencies import get_db, get_settings_dep, require_write_scope
from ...schemas.context import JSONLDResponse
from ...schemas.events import DomainEvent, EventIngestResponse
from ...services.event_service import ingest_event
from ...services.subject import verified_subject_id

router = APIRouter()

# Mounted WITHOUT the read/write scope dependency: a data subject holds no
# `provenance.read` scope, and must not need one to read their own history. The
# route authenticates the person instead, from their verifiable credential.
# Keeping it on a separate router is what stops a scope guard being bolted onto
# it by accident when the main router's mount changes.
subject_router = APIRouter()

MAX_LIMIT = 500


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


def _ld_key(field: str) -> str:
    """`consent_snapshot_hash` → `ds:consentSnapshotHash`."""
    head, *rest = field.split("_")
    return "ds:" + head + "".join(part.title() for part in rest)


def _project(event: DomainEventORM) -> dict[str, Any]:
    """Render a stored event as expanded JSON-LD.

    Projects the event's **own** payload rather than a fixed column list. The
    payload is the validated model dump, so every field an event type declares is
    published the day that type is added — the previous projection emitted four
    columns, which meant `ConsentGranted`, `ConsentRevoked`, `DataIngested` and
    `DataDisclosed` were stored in full and served as four empty values.

    The payload is PII-free by construction (`schemas/events.py`: codes,
    pseudonymous DIDs and hashes only). Keep it that way — this publishes whatever
    an event declares.
    """
    payload = dict(event.payload or {})
    payload.pop("event_type", None)
    payload.pop("event_id", None)
    payload.pop("occurred_at", None)

    projected: dict[str, Any] = {
        "@id": f"urn:event:{event.id}",
        "@type": f"ds:{event.event_type}",
        "ds:occurredAt": event.occurred_at.isoformat(),
    }

    # The indexed columns are the *normalised* dimensions, shared across event
    # types: `DataIngested.dataset_id` and `CataloguePublished.data_product_id`
    # both land in `data_product_id`. Publishing them keeps a reader that filters
    # or groups across types working, and keeps the keys existing clients already
    # read — projecting only the payload silently renamed `ds:dataProductId` to
    # `ds:datasetId` for some types.
    for column, key in (
        (event.agreement_id, "ds:agreementId"),
        (event.data_product_id, "ds:dataProductId"),
        (event.provider_did, "ds:providerDid"),
        (event.consumer_did, "ds:consumerDid"),
        (event.subject_id, "ds:subjectId"),
    ):
        if column is not None:
            projected[key] = column

    # …and then the event's own fields, which is what makes a newly added event
    # type fully visible without touching this route.
    for field, value in payload.items():
        if value is None or value == [] or value == {}:
            continue
        projected.setdefault(_ld_key(field), value)
    return projected


def _filtered(
    stmt,
    *,
    event_type: list[str] | None,
    subject_id: str | None,
    dataset_id: str | None,
    consumer_did: str | None,
    provider_did: str | None,
    agreement_id: str | None,
    occurred_after: datetime | None,
    occurred_before: datetime | None,
):
    if event_type:
        stmt = stmt.where(DomainEventORM.event_type.in_(event_type))
    if subject_id:
        stmt = stmt.where(DomainEventORM.subject_id == subject_id)
    if dataset_id:
        stmt = stmt.where(DomainEventORM.data_product_id == dataset_id)
    if consumer_did:
        stmt = stmt.where(DomainEventORM.consumer_did == consumer_did)
    if provider_did:
        stmt = stmt.where(DomainEventORM.provider_did == provider_did)
    if agreement_id:
        stmt = stmt.where(DomainEventORM.agreement_id == agreement_id)
    if occurred_after:
        stmt = stmt.where(DomainEventORM.occurred_at >= occurred_after)
    if occurred_before:
        stmt = stmt.where(DomainEventORM.occurred_at <= occurred_before)
    return stmt


async def _page(
    db: AsyncSession,
    settings: Settings,
    *,
    limit: int,
    offset: int,
    **filters,
) -> JSONLDResponse:
    total = await db.scalar(_filtered(select(func.count(DomainEventORM.id)), **filters))
    stmt = _filtered(select(DomainEventORM), **filters)
    stmt = stmt.order_by(DomainEventORM.occurred_at.desc()).limit(limit).offset(offset)
    events = (await db.execute(stmt)).scalars().all()

    # `hydra:totalItems` matches what the federated catalogue already publishes,
    # so a client pages both the same way.
    return JSONLDResponse(
        [_project(e) for e in events],
        settings.context_url,
        meta={
            "hydra:totalItems": total or 0,
            "hydra:limit": limit,
            "hydra:offset": offset,
        },
    )


@router.get("/events")
async def list_events(
    event_type: Annotated[list[str] | None, Query()] = None,
    subject_id: str | None = None,
    dataset_id: str | None = None,
    consumer_did: str | None = None,
    provider_did: str | None = None,
    agreement_id: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """The operator view: every event this participant recorded.

    Each participant runs its own provenance store, so this is already scoped to
    one participant by deployment — there is no cross-participant read to guard
    against here. Authorization is the router-level read scope.
    """
    return await _page(
        db,
        settings,
        limit=limit,
        offset=offset,
        event_type=event_type,
        subject_id=subject_id,
        dataset_id=dataset_id,
        consumer_did=consumer_did,
        provider_did=provider_did,
        agreement_id=agreement_id,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )


@subject_router.get("/my/events")
async def list_my_events(
    event_type: Annotated[list[str] | None, Query()] = None,
    dataset_id: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """A data subject's own history — what happened with their data (Art. 15).

    A **separate route**, not a projection of `GET /events`, because it
    authenticates differently: a verified VC-JWT rather than a scope. Overloading
    one route with two authentication models is how a caller ends up reaching data
    it was never granted — the same mistake the retired `X-Api-Key` made.

    `subject_id` is not a parameter here on purpose: it is taken from the verified
    credential, so it cannot be pointed at somebody else.
    """
    subject = verified_subject_id(x_user_vc, x_subject_id, settings)
    return await _page(
        db,
        settings,
        limit=limit,
        offset=offset,
        event_type=event_type,
        subject_id=subject,
        dataset_id=dataset_id,
        consumer_did=None,
        provider_did=None,
        agreement_id=None,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
