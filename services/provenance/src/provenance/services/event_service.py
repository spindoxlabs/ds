"""Domain event → PROV-O materialisation in a single transaction."""
from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AccessLogORM, DomainEventORM, ProvNodeORM, ProvRelationORM
from ..schemas.events import (
    AccessRevoked,
    AccessRequested,
    ActingPrincipal,
    CatalogViewed,
    CataloguePublished,
    ConsentGranted,
    ConsentRevoked,
    ContractAgreementSigned,
    DataDisclosed,
    DataIngested,
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

log = logging.getLogger(__name__)


def content_event_id(event: DomainEvent) -> str:
    """A deterministic idempotency key for an event that carries none.

    Rulebook `L-4` says an event is recorded once and re-posting it is a no-op.
    A caller that omits `event_id` used to be handed a fresh UUID per post, so
    the idempotency check could never match and a retry — the ordinary outcome
    of a timeout on a non-fatal emitter — stored a second copy of the same fact.

    The key is a SHA-256 over the event's own validated payload, `occurred_at`
    included: two events that differ in nothing at all *are* the same event, and
    two that differ in when they happened are not. The `sha256:` prefix keeps a
    derived key distinguishable from a caller-supplied one, which matters when
    reading the table to work out who is retrying.
    """
    payload = event.model_dump(mode="json", exclude={"event_id"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


async def ingest_event(
    session: AsyncSession, event: DomainEvent
) -> EventIngestResponse:
    event_id = event.event_id or content_event_id(event)

    existing = await session.execute(
        select(DomainEventORM).where(DomainEventORM.event_id == event_id)
    )
    if existing.scalar_one_or_none():
        return EventIngestResponse(event_id=event_id, status="duplicate")

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
    elif isinstance(event, ConsentGranted):
        prov_node = await _materialise_consent_granted(session, event)
    elif isinstance(event, ConsentRevoked):
        prov_node = await _materialise_consent_revoked(session, event)
    elif isinstance(event, DataIngested):
        prov_node = await _materialise_data_ingested(session, event)
    elif isinstance(event, DataDisclosed):
        prov_node = await _materialise_data_disclosed(session, event)

    if isinstance(event, QueryExecuted):
        await _record_access_log(session, event)

    orm = DomainEventORM(
        event_type=event.event_type,
        event_id=event_id,
        occurred_at=event.occurred_at,
        payload=event.model_dump(mode="json"),
        prov_node_id=prov_node.id if prov_node else None,
        agreement_id=getattr(event, "agreement_id", None)
        or getattr(event, "agreement_ref", None),
        data_product_id=getattr(event, "data_product_id", None)
        or getattr(event, "dataset_id", None),
        provider_did=getattr(event, "provider_did", None),
        consumer_did=getattr(event, "consumer_did", None),
        subject_id=getattr(event, "subject_id", None),
    )
    session.add(orm)
    await session.flush()

    return EventIngestResponse(
        event_id=event_id,
        status="created",
        prov_node_id=prov_node.id if prov_node else None,
    )


async def _record_access_log(session: AsyncSession, event: QueryExecuted) -> None:
    """Project a `QueryExecuted` into the compliance access log.

    `access_log` is the table `GET /audit/log` and `/audit/log/summary` read, and
    nothing had ever written to it: `POST /audit/log` exists but no component in
    the platform calls it, so both read surfaces answered honestly about an empty
    table (rulebook `L-12`).

    The event that already arrives *is* the query audit — the connector's PEP
    route is literally `POST /internal/audit/query`, and it emits `QueryExecuted`.
    Deriving the log row from it means one write path for one fact, rather than a
    second one every data plane would have to be taught to call.

    A row that cannot name who queried is not a compliance record, so an event
    with no consumer is skipped rather than logged against a placeholder.
    """
    if not event.consumer_did:
        log.info(
            "QueryExecuted for %s names no consumer — no access-log row written",
            event.data_product_id,
        )
        return
    session.add(
        AccessLogORM(
            consumer_id=event.consumer_did,
            dataset_id=event.data_product_id,
            agreement_id=event.agreement_id,
            transfer_id=event.transfer_id,
            subject_ids=event.authorized_subject_ids,
            rows_returned=event.row_count,
            provider_id=event.provider_did,
            logged_at=event.occurred_at,
        )
    )


async def _edge(
    session: AsyncSession,
    relation_type: str,
    subject_id: str,
    object_id: str,
    role: str | None = None,
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
        role=role,
    )
    session.add(rel)


async def _materialise_acting_principal(
    session: AsyncSession,
    activity: ProvNodeORM,
    principal: ActingPrincipal | None,
) -> None:
    """Turn `acted_by` into an agent and the edges that make it answerable.

    Rulebook `L-5`: every principal an event names becomes an agent in the graph.
    `CataloguePublished` and `DataIngested` are the two acts that *decide the
    terms* rather than execute them, which is why they carry a principal at all —
    and it was validated, stored verbatim in the payload, and materialised into
    nothing, so the graph could not answer "who published this offer".

    The agent IRI carries the issuer because a `sub` is only unique within the
    realm that minted it. It stays pseudonymous: an opaque realm-scoped
    identifier, never a name or an address.
    """
    if principal is None:
        return
    iri = (
        f"urn:ds:principal:{principal.issuer}:{principal.subject}"
        if principal.issuer
        else f"urn:ds:principal:{principal.subject}"
    )
    actor = await upsert_node(
        session,
        iri,
        "Agent",
        label=principal.subject,
        external_meta={
            "issuer": principal.issuer,
            "isService": principal.is_service,
        },
    )
    await session.flush()
    await _edge(
        session,
        "wasAssociatedWith",
        activity.id,
        actor.id,
        role="service" if principal.is_service else "actor",
    )
    if principal.on_behalf_of:
        owner = await upsert_node(
            session,
            f"urn:ds:owner:{principal.on_behalf_of}",
            "Agent",
            label=principal.on_behalf_of,
        )
        await session.flush()
        await _edge(session, "actedOnBehalfOf", actor.id, owner.id)


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
    await _edge(session, "wasAssociatedWith", activity.id, publisher.id)
    await _materialise_acting_principal(session, activity, event.acted_by)
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
    # The subject whose access this revoked is named in the event and was the one
    # principal it never became an agent (rulebook `L-5`) — so the graph recorded
    # a revocation with no answer to "whose". `prov:role` distinguishes them from
    # the two parties that *performed* it.
    subject = await upsert_node(
        session, event.subject_id, "Agent", label=event.subject_id
    )
    await session.flush()
    await _edge(session, "invalidated", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, provider.id)
    await _edge(session, "wasAssociatedWith", activity.id, consumer.id)
    await _edge(session, "wasAssociatedWith", activity.id, subject.id, role="dataSubject")
    return activity


async def _materialise_consent_granted(
    session: AsyncSession, event: ConsentGranted
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:consent-grant:{event.event_id or event.occurred_at.isoformat()}",
        "Activity",
        label="Consent Granted",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "datasetId": event.dataset_id,
            "offerId": event.offer_id,
            "purpose": event.purpose,
            "controller": event.controller,
            "controllerRole": event.controller_role,
            "consumerDid": event.consumer_did,
            "legalBasis": event.legal_basis,
        },
    )
    dataset = await upsert_node(
        session, event.dataset_id, "Entity", label=event.dataset_id
    )
    subject = await upsert_node(session, event.subject_id, "Agent", label=event.subject_id)
    await session.flush()
    await _edge(session, "used", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, subject.id)
    return activity


async def _materialise_consent_revoked(
    session: AsyncSession, event: ConsentRevoked
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:consent-revocation:{event.event_id or event.occurred_at.isoformat()}",
        "Activity",
        label="Consent Revoked",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "datasetId": event.dataset_id,
            "offerId": event.offer_id,
            "purpose": event.purpose,
            "controller": event.controller,
            "controllerRole": event.controller_role,
            "consumerDid": event.consumer_did,
            "reason": event.reason,
        },
    )
    dataset = await upsert_node(
        session, event.dataset_id, "Entity", label=event.dataset_id
    )
    subject = await upsert_node(session, event.subject_id, "Agent", label=event.subject_id)
    await session.flush()
    # The subject withdraws the standing permission over the dataset; the
    # revocation invalidates the consent's hold on it.
    await _edge(session, "invalidated", activity.id, dataset.id)
    await _edge(session, "wasAssociatedWith", activity.id, subject.id)
    return activity


async def _materialise_data_ingested(
    session: AsyncSession, event: DataIngested
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:ingestion:{event.event_id or event.occurred_at.isoformat()}",
        "Activity",
        label="Data Ingestion",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "sourceRef": event.source_ref,
            "recordCount": event.record_count,
            "consentSnapshotHash": event.consent_snapshot_hash,
            "agreementRef": event.agreement_ref,
        },
    )
    dataset = await upsert_node(
        session, event.dataset_id, "Entity", label=event.dataset_id,
        energy_type="DataProduct",
    )
    await session.flush()
    await _edge(session, "wasGeneratedBy", dataset.id, activity.id)
    if event.provider_did:
        provider = await upsert_node(
            session, event.provider_did, "Agent", label=event.provider_did
        )
        await session.flush()
        await _edge(session, "wasAssociatedWith", activity.id, provider.id)
        await _edge(session, "wasAttributedTo", dataset.id, provider.id)
    await _materialise_acting_principal(session, activity, event.acted_by)
    return activity


async def _materialise_data_disclosed(
    session: AsyncSession, event: DataDisclosed
) -> ProvNodeORM:
    activity = await upsert_node(
        session,
        f"urn:activity:disclosure:{event.event_id or event.occurred_at.isoformat()}",
        "Activity",
        label="Data Disclosure",
        started_at=event.occurred_at,
        ended_at=event.occurred_at,
        external_meta={
            "datasetId": event.dataset_id,
            "purpose": event.purpose,
            "columns": event.columns,
            "subjectCount": event.subject_count,
            "sourceRef": event.source_ref,
            "consentSnapshotHash": event.consent_snapshot_hash,
            "agreementRef": event.agreement_ref,
        },
    )
    recipient = await upsert_node(
        session, event.recipient_ref, "Agent", label=event.recipient_ref
    )
    await session.flush()
    await _edge(session, "wasAssociatedWith", activity.id, recipient.id)
    # The dataset the snapshot hash is computed over. Without this edge the
    # disclosure hangs off the recipient alone, so "what was disclosed, and
    # under which consent state" is answerable only by reading `external_meta` —
    # and the lineage graph, which is what an auditor traverses, does not connect
    # the handover to the data product at all.
    dataset = await upsert_node(
        session, event.dataset_id, "Entity", label=event.dataset_id,
        energy_type="DataProduct",
    )
    await session.flush()
    await _edge(session, "used", activity.id, dataset.id)
    if event.source_ref:
        source = await upsert_node(
            session, event.source_ref, "Entity", label=event.source_ref
        )
        await session.flush()
        await _edge(session, "used", activity.id, source.id)
    if event.disclosed_by:
        discloser = await upsert_node(
            session, event.disclosed_by, "Agent", label=event.disclosed_by
        )
        await session.flush()
        await _edge(session, "wasAssociatedWith", activity.id, discloser.id)
    return activity
