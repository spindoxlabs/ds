"""Domain event → PROV-O materialisation in a single transaction."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DomainEventORM, ProvNodeORM, ProvRelationORM
from ..schemas.events import (
    AccessRevoked,
    AccessRequested,
    CatalogViewed,
    CataloguePublished,
    ContractAgreementSigned,
    DataTransferCompleted,
    DomainEvent,
    EventIngestResponse,
    NegotiationFinalized,
    NegotiationStarted,
    NegotiationTerminated,
    QueryExecuted,
    TransferStarted,
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
    elif isinstance(event, CatalogViewed):
        prov_node = await _materialise_catalog_viewed(session, event)
    elif isinstance(event, AccessRequested):
        prov_node = await _materialise_access_requested(session, event)
    elif isinstance(event, NegotiationStarted):
        prov_node = await _materialise_negotiation_started(session, event)
    elif isinstance(event, NegotiationFinalized):
        prov_node = await _materialise_negotiation_finalized(session, event)
    elif isinstance(event, NegotiationTerminated):
        prov_node = await _materialise_negotiation_terminated(session, event)
    elif isinstance(event, ContractAgreementSigned):
        prov_node = await _materialise_contract_signed(session, event)
    elif isinstance(event, TransferStarted):
        prov_node = await _materialise_transfer_started(session, event)
    elif isinstance(event, DataTransferCompleted):
        prov_node = await _materialise_transfer_completed(session, event)
    elif isinstance(event, QueryExecuted):
        prov_node = await _materialise_query_executed(session, event)
    elif isinstance(event, UsageObligationFulfilled):
        prov_node = await _materialise_obligation_fulfilled(session, event)
    elif isinstance(event, AccessRevoked):
        prov_node = await _materialise_access_revoked(session, event)

    orm = DomainEventORM(
        event_type=event.event_type,
        event_id=event_id,
        occurred_at=event.occurred_at,
        payload=event.model_dump(mode="json"),
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
    existing = await session.execute(
        select(ProvRelationORM).where(
            ProvRelationORM.relation_type == relation_type,
            ProvRelationORM.subject_id == subject_id,
            ProvRelationORM.object_id == object_id,
        )
    )
    if existing.scalar_one_or_none():
        return
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


async def _materialise_catalog_viewed(
    session: AsyncSession, event: CatalogViewed
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:catalog-view:{event.event_id or event.occurred_at.isoformat()}",
        "Activity",
        label="Catalog Viewed",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "counterPartyAddress": event.counter_party_address,
            "datasetCount": event.dataset_count,
        },
    )
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    await session.flush()
    await _edge(session, "wasAssociatedWith", activity.id, provider.id)
    if event.consumer_did:
        consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
        await session.flush()
        await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    if event.user_did:
        user = await upsert_node(session, event.user_did, "Agent", label=event.user_did)
        await session.flush()
        await _edge(session, "wasAssociatedWith", activity.id, user.id)
    return activity


async def _materialise_access_requested(
    session: AsyncSession, event: AccessRequested
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:access-request:{event.request_id}",
        "Activity",
        label="Access Requested",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "requestId": event.request_id,
            "purpose": event.purpose,
            "offerId": event.offer_id,
        },
    )
    dataset = await upsert_node(session, event.data_product_id, "Entity", label=event.data_product_id)
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    user = await upsert_node(session, event.user_did, "Agent", label=event.user_did)
    await session.flush()
    await _edge(session, "used", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, provider.id)
    await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    await _edge(session, "wasAssociatedWith", activity.id, user.id)
    return activity


async def _materialise_negotiation_started(
    session: AsyncSession, event: NegotiationStarted
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:negotiation:{event.negotiation_id}",
        "Activity",
        label="Negotiation Started",
        started_at=event.occurred_at,
        external_meta={"negotiationId": event.negotiation_id, "offerId": event.offer_id},
    )
    dataset = await upsert_node(session, event.data_product_id, "Entity", label=event.data_product_id)
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "used", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, provider.id)
    await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    if event.user_did:
        user = await upsert_node(session, event.user_did, "Agent", label=event.user_did)
        await session.flush()
        await _edge(session, "wasAssociatedWith", activity.id, user.id)
    return activity


async def _materialise_negotiation_finalized(
    session: AsyncSession, event: NegotiationFinalized
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:negotiation:{event.negotiation_id}",
        "Activity",
        label="Negotiation Finalized",
        ended_at=event.occurred_at,
        external_meta={
            "negotiationId": event.negotiation_id,
            "agreementId": event.agreement_id,
        },
    )
    agreement = await upsert_node(
        session,
        f"urn:entity:agreement:{event.agreement_id}",
        "Entity",
        label=f"Contract Agreement {event.agreement_id}",
        external_meta={"agreementId": event.agreement_id},
    )
    dataset = await upsert_node(session, event.data_product_id, "Entity", label=event.data_product_id)
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "wasGeneratedBy", agreement.id, activity.id)
    await _edge(session, "used", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, provider.id)
    await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    if event.user_did:
        user = await upsert_node(session, event.user_did, "Agent", label=event.user_did)
        await session.flush()
        await _edge(session, "wasAssociatedWith", activity.id, user.id)
    return activity


async def _materialise_negotiation_terminated(
    session: AsyncSession, event: NegotiationTerminated
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:negotiation:{event.negotiation_id}",
        "Activity",
        label="Negotiation Terminated",
        ended_at=event.occurred_at,
        external_meta={
            "negotiationId": event.negotiation_id,
            "reason": event.reason,
        },
    )
    await session.flush()
    for did in [event.provider_did, event.consumer_did, event.user_did]:
        if did:
            agent = await upsert_node(session, did, "Agent", label=did)
            await session.flush()
            await _edge(session, "wasAssociatedWith", activity.id, agent.id)
    if event.data_product_id:
        dataset = await upsert_node(session, event.data_product_id, "Entity", label=event.data_product_id)
        await session.flush()
        await _edge(session, "used", activity.id, dataset.id)
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


async def _materialise_transfer_started(
    session: AsyncSession, event: TransferStarted
) -> ProvNodeORM:
    transfer = await upsert_node(
        session,
        f"urn:activity:transfer:{event.transfer_id}",
        "Activity",
        label="Transfer Started",
        started_at=event.occurred_at,
        external_meta={
            "transferId": event.transfer_id,
            "agreementId": event.agreement_id,
        },
    )
    source = await upsert_node(session, event.data_product_id, "Entity", label=event.data_product_id)
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "used", transfer.id, source.id)
    await _edge(session, "wasAssociatedWith", transfer.id, provider.id)
    await _edge(session, "wasAssociatedWith", transfer.id, consumer.id)
    if event.user_did:
        user = await upsert_node(session, event.user_did, "Agent", label=event.user_did)
        await session.flush()
        await _edge(session, "wasAssociatedWith", transfer.id, user.id)
    return transfer


async def _materialise_query_executed(
    session: AsyncSession, event: QueryExecuted
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:query:{event.event_id or event.transfer_id or event.occurred_at.isoformat()}",
        "Activity",
        label="Query Executed",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "agreementId": event.agreement_id,
            "transferId": event.transfer_id,
            "subjectId": event.subject_id,
            "rowCount": event.row_count,
            "authorizedSubjectIds": event.authorized_subject_ids,
        },
    )
    dataset = await upsert_node(session, event.data_product_id, "Entity", label=event.data_product_id)
    await session.flush()
    await _edge(session, "used", activity.id, dataset.id)
    for did in [event.provider_did, event.consumer_did, event.user_did]:
        if did:
            agent = await upsert_node(session, did, "Agent", label=did)
            await session.flush()
            await _edge(session, "wasAssociatedWith", activity.id, agent.id)
    return activity


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


async def _materialise_access_revoked(
    session: AsyncSession, event: AccessRevoked
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:access-revocation:{event.event_id or event.transfer_id or event.agreement_id}",
        "Activity",
        label="Access Revocation",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "agreementId": event.agreement_id,
            "transferId": event.transfer_id,
            "subjectId": event.subject_id,
            "reason": event.reason,
        },
    )
    dataset = await upsert_node(
        session, event.data_product_id, "Entity", label=event.data_product_id
    )
    provider = await upsert_node(session, event.provider_did, "Agent", label=event.provider_did)
    consumer = await upsert_node(session, event.consumer_did, "Agent", label=event.consumer_did)
    await session.flush()
    await _edge(session, "invalidated", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, provider.id)
    await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    return activity
