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
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)   # Keycloak sub
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[list | None] = mapped_column(JSON)              # list[str]
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
