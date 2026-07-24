from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DidResponse(BaseModel):
    did: str
    did_type: str
    active: bool
    created_at: datetime
    key: dict | None = None
    did_document: dict | None = None


class ParticipantResponse(BaseModel):
    did: str
    dsp_address: str | None
    roles: list[str]
    allowed_scopes: list[str]
    active: bool
    registered_at: datetime


class ParticipantDetailResponse(ParticipantResponse):
    credentials: list[CredentialSummary] = []


class CredentialSummary(BaseModel):
    id: str
    credential_type: str
    status: str
    issued_at: datetime
    expires_at: datetime | None


class CredentialResponse(BaseModel):
    credentialId: str
    subjectDid: str
    issuedAt: datetime
    expiresAt: datetime | None = None


class DataSubjectCredentialResponse(BaseModel):
    subjectDid: str
    credentialId: str
    generatedAt: datetime


class KeyRotationResponse(BaseModel):
    new_kid: str
    old_kid: str


class ParticipantCheckResponse(BaseModel):
    allowed: bool


class KeycloakMappingResponse(BaseModel):
    did: str
    keycloak_realm: str
    keycloak_user_id: str
    email: str | None
    subject_id: str


class UserResolveResponse(BaseModel):
    did: str
    role: str | None = None
    vc_jws: str | None = None
    subject_id: str


class MembershipResponse(BaseModel):
    user_did: str
    organization_alias: str
    role: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class MembershipCheckResponse(BaseModel):
    member: bool


class OwnerResponse(BaseModel):
    id: str
    type: str
    name: str
    did: str | None
    url: str | None
    aliases: list[str]
    organization_config: dict | None
    canonical_uri: str | None = None
    # ── Gaia-X legal identity + lifecycle (Block D) ───────────────
    registration_number: str | None = None
    registration_type: str | None = None
    hq_country_code: str | None = None
    legal_country_code: str | None = None
    parent_organizations: list[str] | None = None
    sub_organizations: list[str] | None = None
    status: str = "verified"
    verified_at: datetime | None = None
    verified_by: str | None = None
    evidence_ref: str | None = None
    agreement_id: str | None = None
    agreement_version: str | None = None
    agreement_accepted_at: datetime | None = None
    agreement_capacity: str | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationApplicationResponse(BaseModel):
    id: str
    alias: str
    legal_name: str
    registration_number: str | None = None
    registration_type: str | None = None
    hq_country_code: str | None = None
    legal_country_code: str | None = None
    parent_organizations: list[str] | None = None
    sub_organizations: list[str] | None = None
    roles: list[str]
    did: str | None = None
    dsp_address: str | None = None
    status: str
    evidence_ref: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class AgreementResponse(BaseModel):
    id: str
    version: str
    effective_from: date | None = None
    applies_to: list[str]
    capacity: str
    texts: dict
    created_at: datetime
    updated_at: datetime


class AgreementAcceptanceResponse(BaseModel):
    id: str
    owner_alias: str
    agreement_id: str
    agreement_version: str
    capacity: str
    locale: str
    text_sha256: str
    accepted_by: str | None = None
    accepted_at: datetime
