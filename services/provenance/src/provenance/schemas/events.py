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


class ContractAgreementSigned(BaseModel):
    event_type: Literal["ContractAgreementSigned"] = "ContractAgreementSigned"
    event_id: str | None = None
    occurred_at: datetime
    agreement_id: str
    data_product_id: str
    provider_did: str
    consumer_did: str
    policy_hash: str | None = None


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


class UsageObligationFulfilled(BaseModel):
    event_type: Literal["UsageObligationFulfilled"] = "UsageObligationFulfilled"
    event_id: str | None = None
    occurred_at: datetime
    agreement_id: str
    consumer_did: str
    obligation_type: str          # e.g. "odrl:delete", "odrl:attribute"


DomainEvent = Annotated[
    CataloguePublished
    | ContractAgreementSigned
    | DataTransferCompleted
    | UsageObligationFulfilled,
    Field(discriminator="event_type"),
]


class EventIngestResponse(BaseModel):
    event_id: str
    status: Literal["created", "duplicate"]
    prov_node_id: str | None = None
