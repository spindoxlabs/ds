from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .engine import Base

JsonType = JSONB().with_variant(JSON(), "sqlite")


class Key(Base):
    __tablename__ = "keys"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_did: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ES256"
    )
    private_jwk: Mapped[dict] = mapped_column(JsonType, nullable=False)
    public_jwk: Mapped[dict] = mapped_column(JsonType, nullable=False)
    kid: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Did(Base):
    __tablename__ = "dids"

    did: Mapped[str] = mapped_column(Text, primary_key=True)
    did_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # 'participant' | 'user'
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_endpoints: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    key_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("keys.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    key: Mapped[Key | None] = relationship("Key", lazy="joined")
    credentials: Mapped[list[Credential]] = relationship(
        "Credential",
        foreign_keys="Credential.subject_did",
        back_populates="subject",
        lazy="selectin",
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    credential_type: Mapped[str] = mapped_column(String(64), nullable=False)
    issuer_did: Mapped[str] = mapped_column(Text, nullable=False)
    subject_did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), nullable=False
    )
    credential_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )
    status_list_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    subject: Mapped[Did] = relationship(
        "Did", back_populates="credentials", lazy="joined"
    )


class Participant(Base):
    __tablename__ = "participants"

    did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), primary_key=True
    )
    dsp_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    roles: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    allowed_scopes: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    sts_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    did_record: Mapped[Did] = relationship("Did", lazy="joined")


class KeycloakMapping(Base):
    __tablename__ = "keycloak_mappings"

    did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), primary_key=True
    )
    keycloak_realm: Mapped[str] = mapped_column(Text, nullable=False)
    keycloak_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="schema:Organization"
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    did: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    organization_config: Mapped[dict | None] = mapped_column(
        JsonType, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    user_did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), primary_key=True
    )
    organization_alias: Mapped[str] = mapped_column(
        String, primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StatusList(Base):
    __tablename__ = "status_lists"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default="revocation"
    )
    bitstring: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
