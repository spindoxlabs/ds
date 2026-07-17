from __future__ import annotations

from pydantic import BaseModel, Field


class CreateDidRequest(BaseModel):
    did: str
    did_type: str = Field(pattern=r"^(participant|user)$")
    display_name: str | None = None
    service_endpoints: list[dict] | None = None


class CreateParticipantRequest(BaseModel):
    did: str
    dsp_address: str | None = None
    role: str = Field(pattern=r"^(provider|consumer)$")
    allowed_scopes: list[str] = []


class UpdateParticipantRequest(BaseModel):
    dsp_address: str | None = None
    role: str | None = None
    allowed_scopes: list[str] | None = None
    active: bool | None = None


class IssueMembershipRequest(BaseModel):
    subject_did: str
    role: str = "consumer"
    allowed_scopes: list[str] = ["dataspaces.query"]
    ttl_days: int | None = None


class IssueDataSubjectRequest(BaseModel):
    subject_id: str
    role: str | None = None
    linked_participant_did: str | None = None
    allowed_actions: list[str] | None = None
    ttl_days: int | None = None


class KeycloakSyncRequest(BaseModel):
    did: str
    keycloak_realm: str
    keycloak_user_id: str
    email: str | None = None


class CreateOwnerRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    type: str = "schema:Organization"
    name: str
    did: str | None = None
    url: str | None = None
    aliases: list[str] = []
    organization_config: dict | None = None


class UpdateOwnerRequest(BaseModel):
    type: str | None = None
    name: str | None = None
    did: str | None = None
    url: str | None = None
    aliases: list[str] | None = None
    organization_config: dict | None = None


class CreateMembershipRequest(BaseModel):
    user_did: str
    organization_alias: str
    role: str | None = None
