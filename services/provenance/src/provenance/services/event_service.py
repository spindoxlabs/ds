"""Domain event → PROV-O materialisation in a single transaction."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DomainEventORM, ProvNodeORM, ProvRelationORM
from ..schemas.events import (
    CataloguePublished,
    ContractAgreementSigned,
    DataTransferCompleted,
    DomainEvent,
    EventIngestResponse,
    UsageObligationFulfilled,
)
from .prov_service import upsert_node


async def ingest_event(
    session: AsyncSession, event: DomainEvent
) -> EventIngestResponse:
    # Idempotency check
    if event.event_id:
        existing = await session.execute(
            select(DomainEventORM).where(DomainEventORM.event_id == event.event_id)
        )
        if existing.scalar_one_or_none():
            return EventIngestResponse(
                event_id=event.event_id, status="duplicate"
            )

    event_id = event.event_id or str(uuid.uuid4())
    prov_node: ProvNodeORM | None = None

    if isinstance(event, CataloguePublished):
        prov_node = await _materialise_catalogue_published(session, event)
    elif isinstance(event, ContractAgreementSigned):
        prov_node = await _materialise_contract_signed(session, event)
    elif isinstance(event, DataTransferCompleted):
        prov_node = await _materialise_transfer_completed(session, event)
    elif isinstance(event, UsageObligationFulfilled):
        prov_node = await _materialise_obligation_fulfilled(session, event)

    orm = DomainEventORM(
        event_type=event.event_type,
        event_id=event_id,
        occurred_at=event.occurred_at,
        payload=event.model_dump(),
        prov_node_id=prov_node.id if prov_node else None,
        agreement_id=getattr(event, "agreement_id", None),
        data_product_id=getattr(event, "data_product_id", None),
        provider_did=getattr(event, "provider_did", None),
        consumer_did=getattr(event, "consumer_did", None),
        processed=True,
    )
    session.add(orm)
    await session.flush()

    return EventIngestResponse(
        event_id=event_id,
        status="created",
        prov_node_id=prov_node.id if prov_node else None,
    )


async def _edge(
    session: AsyncSession,
    relation_type: str,
    subject_id: str,
    object_id: str,
) -> None:
    rel = ProvRelationORM(
        relation_type=relation_type,
        subject_id=subject_id,
        object_id=object_id,
    )
    session.add(rel)


async def _materialise_catalogue_published(
    session: AsyncSession, event: CataloguePublished
) -> ProvNodeORM:
    dataset = await upsert_node(
        session, event.data_product_id, "Entity",
        label=event.title, description=event.description,
        energy_type="DataProduct",
    )
    activity = await upsert_node(
        session,
        f"urn:activity:catalogue-publication:{event.data_product_id}",
        "Activity",
        label="Catalogue Publication",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
    )
    publisher = await upsert_node(
        session, event.provider_did, "Agent", label=event.provider_did
    )
    await session.flush()
    await _edge(session, "wasGeneratedBy", dataset.id, activity.id)
    await _edge(session, "wasAttributedTo", dataset.id, publisher.id)
    return activity


async def _materialise_contract_signed(
    session: AsyncSession, event: ContractAgreementSigned
) -> ProvNodeORM:
    negotiation = await upsert_node(
        session,
        f"urn:activity:negotiation:{event.agreement_id}",
        "Activity",
        label="Contract Negotiation",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={"policyHash": event.policy_hash},
    )
    agreement = await upsert_node(
        session,
        f"urn:entity:agreement:{event.agreement_id}",
        "Entity",
        label=f"Contract Agreement {event.agreement_id}",
        external_meta={"agreementId": event.agreement_id},
    )
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "wasGeneratedBy", agreement.id, negotiation.id)
    await _edge(session, "wasAssociatedWith", negotiation.id, provider.id)
    await _edge(session, "wasAssociatedWith", negotiation.id, consumer.id)
    return negotiation


async def _materialise_transfer_completed(
    session: AsyncSession, event: DataTransferCompleted
) -> ProvNodeORM:
    transfer = await upsert_node(
        session,
        f"urn:activity:transfer:{event.transfer_id}",
        "Activity",
        label="Data Transfer",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "transferId": event.transfer_id,
            "bytesTransferred": event.bytes_transferred,
        },
    )
    derived_iri = (
        event.derived_dataset_iri
        or f"urn:entity:derived:{event.data_product_id}:{event.consumer_did}"
    )
    derived = await upsert_node(
        session, derived_iri, "Entity",
        label=f"Derived dataset at {event.consumer_did}",
        energy_type="DerivedDataset",
    )
    source = await upsert_node(
        session, event.data_product_id, "Entity", label=event.data_product_id
    )
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "wasGeneratedBy", derived.id, transfer.id)
    await _edge(session, "wasDerivedFrom", derived.id, source.id)
    await _edge(session, "wasAttributedTo", derived.id, consumer.id)
    return transfer


async def _materialise_obligation_fulfilled(
    session: AsyncSession, event: UsageObligationFulfilled
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:obligation:{event.agreement_id}:{event.obligation_type}",
        "Activity",
        label=f"Obligation: {event.obligation_type}",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={"obligationType": event.obligation_type},
    )
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    return activity
