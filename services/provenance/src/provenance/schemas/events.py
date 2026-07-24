"""Domain event schemas — one per DSSC lifecycle event."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class CataloguePublished(BaseModel):
    event_type: Literal["CataloguePublished"] = "CataloguePublished"
    event_id: str | None = None
    occurred_at: datetime
    data_product_id: str          # IRI of the published dataset/asset
    provider_did: str
    title: str | None = None
    description: str | None = None


class CatalogViewed(BaseModel):
    event_type: Literal["CatalogViewed"] = "CatalogViewed"
    event_id: str | None = None
    occurred_at: datetime
    provider_did: str
    consumer_did: str | None = None
    user_did: str | None = None
    counter_party_address: str | None = None
    dataset_count: int | None = None


class AccessRequested(BaseModel):
    event_type: Literal["AccessRequested"] = "AccessRequested"
    event_id: str | None = None
    occurred_at: datetime
    request_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    user_did: str
    purpose: list[str] = []
    offer_id: str | None = None


class NegotiationStarted(BaseModel):
    event_type: Literal["NegotiationStarted"] = "NegotiationStarted"
    event_id: str | None = None
    occurred_at: datetime
    negotiation_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    user_did: str | None = None
    offer_id: str | None = None


class NegotiationFinalized(BaseModel):
    event_type: Literal["NegotiationFinalized"] = "NegotiationFinalized"
    event_id: str | None = None
    occurred_at: datetime
    negotiation_id: str
    agreement_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    user_did: str | None = None


class NegotiationTerminated(BaseModel):
    event_type: Literal["NegotiationTerminated"] = "NegotiationTerminated"
    event_id: str | None = None
    occurred_at: datetime
    negotiation_id: str
    data_product_id: str | None = None
    provider_did: str | None = None
    consumer_did: str | None = None
    user_did: str | None = None
    reason: str | None = None


class ContractAgreementSigned(BaseModel):
    event_type: Literal["ContractAgreementSigned"] = "ContractAgreementSigned"
    event_id: str | None = None
    occurred_at: datetime
    agreement_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    policy_hash: str | None = None


class TransferStarted(BaseModel):
    event_type: Literal["TransferStarted"] = "TransferStarted"
    event_id: str | None = None
    occurred_at: datetime
    transfer_id: str
    agreement_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    user_did: str | None = None


class DataTransferCompleted(BaseModel):
    event_type: Literal["DataTransferCompleted"] = "DataTransferCompleted"
    event_id: str | None = None
    occurred_at: datetime
    transfer_id: str
    agreement_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    bytes_transferred: int | None = None
    derived_dataset_iri: str | None = None  # IRI of the dataset copy at consumer


class QueryExecuted(BaseModel):
    event_type: Literal["QueryExecuted"] = "QueryExecuted"
    event_id: str | None = None
    occurred_at: datetime
    data_product_id: str
    provider_did: str | None = None
    consumer_did: str | None = None
    user_did: str | None = None
    subject_id: str | None = None
    agreement_id: str | None = None
    transfer_id: str | None = None
    row_count: int | None = None
    authorized_subject_ids: list[str] | None = None


class UsageObligationFulfilled(BaseModel):
    event_type: Literal["UsageObligationFulfilled"] = "UsageObligationFulfilled"
    event_id: str | None = None
    occurred_at: datetime
    agreement_id: str
    consumer_did: str
    obligation_type: str          # e.g. "odrl:delete", "odrl:attribute"


class AccessRevoked(BaseModel):
    event_type: Literal["AccessRevoked"] = "AccessRevoked"
    event_id: str | None = None
    occurred_at: datetime
    agreement_id: str | None = None
    transfer_id: str | None = None
    data_product_id: str
    provider_did: str
    consumer_did: str
    subject_id: str
    reason: str | None = None


# ── Consent & disclosure events (Block C) ─────────────────────────────────────
#
# These record the legal chain — when a subject's consent was granted or
# revoked, and when data actually changed hands under it — as auditable PROV-O.
# They carry **codes, DIDs and hashes only, never PII**: ``subject_id`` is the
# pseudonymous subject DID (as on ``AccessRevoked``), ``legal_basis`` holds the
# Block B evidence record (basis IRI, versions, hashes), and
# ``consent_snapshot_hash`` is a SHA-256 over the sorted consent tuples that
# authorised a handover — verifiable by recomputation, holding no name or POD.


class ConsentGranted(BaseModel):
    event_type: Literal["ConsentGranted"] = "ConsentGranted"
    event_id: str | None = None
    occurred_at: datetime
    subject_id: str               # pseudonymous subject DID
    dataset_id: str               # governance key the consent is about
    consumer_did: str | None = None  # the party admitted, or "*" for the scoped wildcard
    offer_id: str | None = None
    purpose: list[str] = []
    controller: str | None = None
    controller_role: str | None = None
    legal_basis: dict | None = None  # codes/hashes only (Block B evidence)


class ConsentRevoked(BaseModel):
    event_type: Literal["ConsentRevoked"] = "ConsentRevoked"
    event_id: str | None = None
    occurred_at: datetime
    subject_id: str
    dataset_id: str
    consumer_did: str | None = None
    offer_id: str | None = None
    purpose: list[str] = []
    controller: str | None = None
    controller_role: str | None = None
    reason: str | None = None


class DataIngested(BaseModel):
    event_type: Literal["DataIngested"] = "DataIngested"
    event_id: str | None = None
    occurred_at: datetime
    dataset_id: str
    provider_did: str | None = None
    source_ref: str | None = None        # opaque handle for the source handover, never PII
    record_count: int | None = None
    consent_snapshot_hash: str | None = None  # SHA-256 over the authorising consent tuples
    agreement_ref: str | None = None     # identifies the DPA, never its contents


class DataDisclosed(BaseModel):
    event_type: Literal["DataDisclosed"] = "DataDisclosed"
    event_id: str | None = None
    occurred_at: datetime
    recipient_ref: str                   # who received the data (org alias/DID/DPA ref)
    purpose: list[str] = []
    columns: list[str] = []              # disclosed column *names*, not values (Art. 13/14)
    subject_count: int | None = None
    source_ref: str | None = None        # what was disclosed (e.g. a REC slug), never PII
    disclosed_by: str | None = None      # the disclosing agent (e.g. the REC controller)
    consent_snapshot_hash: str | None = None
    agreement_ref: str | None = None


DomainEvent = Annotated[
    CataloguePublished
    | CatalogViewed
    | AccessRequested
    | NegotiationStarted
    | NegotiationFinalized
    | NegotiationTerminated
    | ContractAgreementSigned
    | TransferStarted
    | DataTransferCompleted
    | QueryExecuted
    | UsageObligationFulfilled
    | AccessRevoked
    | ConsentGranted
    | ConsentRevoked
    | DataIngested
    | DataDisclosed,
    Field(discriminator="event_type"),
]


class EventIngestResponse(BaseModel):
    event_id: str
    status: Literal["created", "duplicate"]
    prov_node_id: str | None = None
