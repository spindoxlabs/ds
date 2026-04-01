"""SQLAlchemy ORM models for ds-provenance."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .engine import Base

# Use JSONB on Postgres, JSON on SQLite
JsonType = JSONB().with_variant(JSON(), "sqlite")


def _uuid() -> str:
    return str(uuid.uuid4())


class ProvNodeORM(Base):
    """Unified Entity / Activity / Agent table."""

    __tablename__ = "prov_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    iri: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)  # Entity|Activity|Agent
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    energy_type: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_meta: Mapped[dict | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subject_relations: Mapped[list[ProvRelationORM]] = relationship(
        "ProvRelationORM", foreign_keys="ProvRelationORM.subject_id", back_populates="subject"
    )
    object_relations: Mapped[list[ProvRelationORM]] = relationship(
        "ProvRelationORM", foreign_keys="ProvRelationORM.object_id", back_populates="object"
    )


class ProvRelationORM(Base):
    """PROV-O edges (all 7 relation types)."""

    __tablename__ = "prov_relations"
    __table_args__ = (
        UniqueConstraint("relation_type", "subject_id", "object_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(ForeignKey("prov_nodes.id"), nullable=False)
    object_id: Mapped[str] = mapped_column(ForeignKey("prov_nodes.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    subject: Mapped[ProvNodeORM] = relationship(
        "ProvNodeORM", foreign_keys=[subject_id], back_populates="subject_relations"
    )
    object: Mapped[ProvNodeORM] = relationship(
        "ProvNodeORM", foreign_keys=[object_id], back_populates="object_relations"
    )


class DomainEventORM(Base):
    """Raw domain event log with idempotency key."""

    __tablename__ = "domain_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str | None] = mapped_column(Text, unique=True)  # caller idempotency key
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False)
    prov_node_id: Mapped[str | None] = mapped_column(ForeignKey("prov_nodes.id"))
    agreement_id: Mapped[str | None] = mapped_column(Text)
    data_product_id: Mapped[str | None] = mapped_column(Text)
    provider_did: Mapped[str | None] = mapped_column(Text)
    consumer_did: Mapped[str | None] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class AccessLogORM(Base):
    """Compliance audit log for dataspace-originated queries."""

    __tablename__ = "access_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    agreement_id: Mapped[str | None] = mapped_column(Text)
    transfer_id: Mapped[str | None] = mapped_column(Text)
    query_params: Mapped[dict | None] = mapped_column(JsonType)
    subject_ids: Mapped[list | None] = mapped_column(JsonType)  # list[str]
    rows_returned: Mapped[int | None] = mapped_column(Integer)
    response_status: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    provider_id: Mapped[str | None] = mapped_column(Text)
