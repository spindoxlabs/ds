"""SQLAlchemy ORM models for ds-connector."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .engine import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ContractAgreementORM(Base):
    """Persisted EDC contract agreement for PEP + audit."""

    __tablename__ = "contract_agreements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agreement_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    termination_reason: Mapped[str | None] = mapped_column(Text)


class ConsentRequestORM(Base):
    """Consent request from a consumer for a data subject's data."""

    __tablename__ = "consent_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)   # User DID
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Purpose slugs from the ODRL profile taxonomy, validated on write.
    # An empty list is never a wildcard: for a consent-required dataset it means
    # the person was never told the use, so the row fails closed.
    purpose: Mapped[list | None] = mapped_column(JSON)              # list[str]
    # Who decides the purpose. `controller` is an owner alias; `controller_role`
    # names which of that participant's roles is acting, because controller is
    # not the same thing as legal entity — a DSO's grid-operations and metering
    # functions are distinct controllers under unbundling rules.
    controller: Mapped[str | None] = mapped_column(Text)
    controller_role: Mapped[str | None] = mapped_column(Text)
    # The sharing offer this row was created from, when it came from one.
    offer_id: Mapped[str | None] = mapped_column(Text)
    # Evidence of the legal basis under which this row was written: the DPV
    # basis IRI plus the codes + versions + hashes that prove *what* was shown
    # and agreed. Never PII — `submission_ref` only, never a name, email, CF or
    # POD. The connector DB is not a PII store.
    legal_basis: Mapped[dict | None] = mapped_column(JSON)
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # pending | granted | rejected | revoked
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_url: Mapped[str | None] = mapped_column(Text)      # webhook target
    transfer_ids: Mapped[list | None] = mapped_column(JSON)         # list[str]


class ConsumerTransferORM(Base):
    """Transfer ownership for user-scoped consumer views."""

    __tablename__ = "consumer_transfers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    transfer_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_agreement_id: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConsumerAccessRequestORM(Base):
    """User-scoped access request started from the consumer catalogue."""

    __tablename__ = "consumer_access_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    counter_party_address: Mapped[str] = mapped_column(Text, nullable=False)
    offer_id: Mapped[str] = mapped_column(Text, nullable=False)
    assigner: Mapped[str] = mapped_column(Text, nullable=False)
    negotiation_id: Mapped[str | None] = mapped_column(Text, unique=True)
    contract_agreement_id: Mapped[str | None] = mapped_column(Text)
    transfer_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="negotiating")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
