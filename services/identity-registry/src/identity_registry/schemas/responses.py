from __future__ import annotations

from datetime import datetime

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
    role: str
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
