from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

VALID_ROLES = {"provider", "consumer"}
# Gaia-X gx:LegalParticipant registration types (§5.1), adopted verbatim.
VALID_REGISTRATION_TYPES = {"local", "EUID", "EORI", "vatID", "leiCode"}
# Consent capacities (§2.5) — decides coverage vs. its-own-consent.
VALID_CAPACITIES = {"processor", "joint_controller", "independent_controller"}


class CreateDidRequest(BaseModel):
    did: str
    did_type: str = Field(pattern=r"^(participant|user)$")
    display_name: str | None = None
    service_endpoints: list[dict] | None = None


class CreateParticipantRequest(BaseModel):
    did: str
    dsp_address: str | None = None
    roles: list[str] = Field(min_length=1)
    allowed_scopes: list[str] = []

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_ROLES
        if invalid:
            raise ValueError(f"Invalid roles: {invalid}. Must be one of {VALID_ROLES}")
        return sorted(set(v))


class UpdateParticipantRequest(BaseModel):
    dsp_address: str | None = None
    roles: list[str] | None = None
    allowed_scopes: list[str] | None = None
    active: bool | None = None

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("roles must not be empty")
        invalid = set(v) - VALID_ROLES
        if invalid:
            raise ValueError(f"Invalid roles: {invalid}. Must be one of {VALID_ROLES}")
        return sorted(set(v))


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


# ── Organisation onboarding (Block D) ─────────────────────────────


def _validate_registration_type(v: str | None) -> str | None:
    if v is not None and v not in VALID_REGISTRATION_TYPES:
        raise ValueError(
            f"Invalid registration_type: {v!r}. "
            f"Must be one of {sorted(VALID_REGISTRATION_TYPES)}"
        )
    return v


def _validate_roles(v: list[str]) -> list[str]:
    invalid = set(v) - VALID_ROLES
    if invalid:
        raise ValueError(f"Invalid roles: {invalid}. Must be one of {VALID_ROLES}")
    return sorted(set(v))


class CreateOrganizationApplicationRequest(BaseModel):
    alias: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    legal_name: str
    registration_number: str | None = None
    registration_type: str | None = None
    hq_country_code: str | None = None
    legal_country_code: str | None = None
    parent_organizations: list[str] = []
    sub_organizations: list[str] = []
    roles: list[str] = Field(default_factory=lambda: ["consumer"], min_length=1)
    did: str | None = None
    dsp_address: str | None = None
    notes: str | None = None

    @field_validator("registration_type")
    @classmethod
    def _reg_type(cls, v: str | None) -> str | None:
        return _validate_registration_type(v)

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: list[str]) -> list[str]:
        return _validate_roles(v)


class UpdateOrganizationApplicationRequest(BaseModel):
    """Partial update of an application — including the verify transition.

    Setting ``status`` to ``verified`` requires ``verified_by``; the endpoint
    stamps ``verified_at``. Promotion into an ``Owner`` row is a separate step.
    """

    legal_name: str | None = None
    registration_number: str | None = None
    registration_type: str | None = None
    hq_country_code: str | None = None
    legal_country_code: str | None = None
    parent_organizations: list[str] | None = None
    sub_organizations: list[str] | None = None
    roles: list[str] | None = None
    did: str | None = None
    dsp_address: str | None = None
    status: str | None = None
    evidence_ref: str | None = None
    verified_by: str | None = None
    notes: str | None = None

    @field_validator("registration_type")
    @classmethod
    def _reg_type(cls, v: str | None) -> str | None:
        return _validate_registration_type(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v is not None and v not in {"pending", "verified", "rejected"}:
            raise ValueError("status must be pending | verified | rejected")
        return v

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _validate_roles(v)


class IssueOrganizationCredentialRequest(BaseModel):
    """Issue an OrganizationCredential for a verified owner (§5.5).

    The endpoint reads the owner's legal identity from the DB; the caller only
    names the alias and an optional TTL. Fields may override the stored roles /
    scopes for the credential.
    """

    alias: str
    roles: list[str] | None = None
    allowed_scopes: list[str] | None = None
    dsp_address: str | None = None
    ttl_days: int | None = None

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _validate_roles(v)


class PromoteOwnerRequest(BaseModel):
    """Register a verified, credentialled owner as a DSP participant (§5.6).

    Gate enforced server-side: a valid, unrevoked OrganizationCredential must
    exist first."""

    dsp_address: str
    roles: list[str] | None = None
    allowed_scopes: list[str] = ["dataspaces.query"]
    sts_secret: str = "insecure-dev-secret"

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _validate_roles(v)


class AcceptAgreementRequest(BaseModel):
    """Record an organisation's acceptance of an agreement version over HTTP,
    the same operation ``ir-cli org agreement`` performs on the DB (§5.4)."""

    agreement_id: str
    version: str
    locale: str = "en"
    accepted_by: str | None = None


class PatchOwnerRequest(BaseModel):
    """Promote / update the Gaia-X + lifecycle fields on an Owner (§5.5).

    Distinct from ``UpdateOwnerRequest`` (which covers the base registry
    fields): this carries the verification lifecycle, legal identity and
    current-agreement columns.
    """

    name: str | None = None
    did: str | None = None
    url: str | None = None
    registration_number: str | None = None
    registration_type: str | None = None
    hq_country_code: str | None = None
    legal_country_code: str | None = None
    parent_organizations: list[str] | None = None
    sub_organizations: list[str] | None = None
    status: str | None = None
    verified_by: str | None = None
    evidence_ref: str | None = None

    @field_validator("registration_type")
    @classmethod
    def _reg_type(cls, v: str | None) -> str | None:
        return _validate_registration_type(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v is not None and v not in {"pending", "verified", "suspended", "revoked"}:
            raise ValueError("status must be pending | verified | suspended | revoked")
        return v
