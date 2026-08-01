"""Domain event schemas — one per DSSC lifecycle event."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ActingPrincipal(BaseModel):
    """Who performed an act that *determined* how data may be processed.

    Every other event names the **participant** — `provider_did`, `subject_did` —
    which answers "which organisation" and never "which human". That is enough for
    a disclosure, where the organisation is the controller. It is not enough for
    the acts that decide *what the terms are*: publishing a catalogue turns
    `governance.yaml` into ODRL offers, with the purposes and the assigner that
    every later disclosure is evaluated against.

    Under GDPR Art. 5(2) an operator has to be able to answer "who could have
    published this offer, and for which organisation were they acting" — and until
    now the system could answer neither. That is the whole reason this exists.

    **Pseudonymous by construction.** The subject claim is an opaque realm-scoped
    identifier, not a name, an email or a username, and it is recorded with the
    issuer that minted it because a `sub` means nothing without its realm. Resolving
    it back to a person needs realm access, which is exactly the separation the rest
    of the provenance model already keeps (`docs/rulebook/provenance-and-logging.md`
    `L-3`: codes, pseudonymous DIDs and hashes only — never PII).
    """

    subject: str
    """The token's `sub`. Opaque, realm-scoped, never a name or an address."""

    issuer: str | None = None
    """The realm that minted it. A `sub` is only unique within its issuer."""

    on_behalf_of: str | None = None
    """The `Owner` id the actor claimed to act for, when the act was owner-scoped.

    The claim, not a verification — the perimeter is what verifies it. Recording it
    is what makes "acting for whom" answerable at all.
    """

    is_service: bool = False
    """True when a service client acted, so an automated publish is not mistaken
    for a person's decision."""


class CataloguePublished(BaseModel):
    event_type: Literal["CataloguePublished"] = "CataloguePublished"
    event_id: str | None = None
    occurred_at: datetime
    data_product_id: str          # IRI of the published dataset/asset
    provider_did: str
    title: str | None = None
    description: str | None = None
    # Who published it. Optional so a deployment that predates this keeps
    # validating, and so an automated publish is recorded honestly as one.
    acted_by: ActingPrincipal | None = None


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
    """A consumer asked for access — and, optionally, said why.

    ``purpose`` is what the **offer** permits, read from its ``odrl:purpose``
    constraint. For a multi-purpose dataset that is a set, and a set cannot
    answer "why was this data requested". ``declared_purpose`` is the consumer's
    own statement, validated at request time against that set, so it is never
    broader than what the offer allowed.

    ``justification_ref`` is an opaque external reference. The justification
    text itself is never emitted here — this store holds codes, DIDs and hashes.
    """

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
    declared_purpose: list[str] = []
    declared_from: datetime | None = None
    declared_until: datetime | None = None
    justification_ref: str | None = None


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
    # An offline handover is recorded *by a person*; without this the record says
    # a participant ingested data and cannot say who decided to.
    acted_by: ActingPrincipal | None = None


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
