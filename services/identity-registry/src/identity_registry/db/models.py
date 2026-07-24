from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
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
    # ── Gaia-X-shaped legal identity (Block D) ────────────────────────
    # Shape-compatible with gx:LegalParticipant; not full GXDCH compliance.
    registration_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # local | EUID | EORI | vatID | leiCode
    hq_country_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )  # ISO 3166-2
    legal_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    parent_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    sub_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    # ── Verification lifecycle ────────────────────────────────────────
    # Operator-seeded owners default to 'verified'; owners promoted from an
    # OrganizationApplication move pending → verified → suspended | revoked.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="verified", server_default="verified"
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── Current accepted service agreement + declared capacity (§2.5) ──
    agreement_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    agreement_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agreement_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agreement_capacity: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # processor | joint_controller | independent_controller
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrganizationApplication(Base):
    """Pre-verification organisation registration data (Block D §5.5).

    Holds an applicant's declared legal identity before it is promoted into an
    ``Owner`` row on verification. All trust state (the ``status`` transition to
    ``verified``) lives here and in the ``Owner`` it promotes into — never in the
    portal or CLI, which only call the IR.
    """

    __tablename__ = "organization_applications"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    registration_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hq_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    legal_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    parent_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    sub_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    roles: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    did: Mapped[str | None] = mapped_column(Text, nullable=True)
    dsp_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending | verified | rejected
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Agreement(Base):
    """Service-agreement definition, YAML-seeded and IR-hosted (Block D §5.4).

    Shaped so it can later become a ``gx:GaiaXTermsAndConditions`` credential.
    The ``capacity`` field is the consent boundary (§2.5): it decides whether a
    party accepting this agreement is covered-and-disclosed or needs its own
    consent.
    """

    __tablename__ = "agreements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    effective_from: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    applies_to: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    capacity: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # processor | joint_controller | independent_controller
    # {locale: {"path": str, "sha256": str}} — codes + hash, never inline PII.
    texts: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgreementAcceptance(Base):
    """An organisation's acceptance of a specific agreement version (§5.4).

    Same evidence shape as the citizen path (§2.4): proves *what text, at what
    version and locale* was accepted via ``text_sha256`` — no prose, no PII.
    """

    __tablename__ = "agreement_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "owner_alias",
            "agreement_id",
            "agreement_version",
            name="uq_agreement_acceptance",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agreement_id: Mapped[str] = mapped_column(String, nullable=False)
    agreement_version: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(
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
