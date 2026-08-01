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


class UserCredentialResponse(BaseModel):
    """One presentable credential held by a user."""

    role: str | None = None
    vc_jws: str | None = None
    credential_type: str
    issued_at: datetime
    expires_at: datetime | None = None


class UserResolveResponse(BaseModel):
    """Every credential a user can present, not just the newest one.

    A person legitimately holds more than one role — the same human can be a
    data subject about their own consumption *and* a consumer user acting for an
    organisation. Returning only the most recently issued credential made those
    mutually exclusive for every caller, and left a caller presenting whichever
    VC happened to be newest rather than the one the operation requires.

    ``role`` and ``vc_jws`` are retained as the newest entry of ``credentials``
    so existing callers keep working; new callers should read ``credentials`` and
    select by role.
    """

    did: str | None = None
    subject_id: str
    roles: list[str] = []
    credentials: list[UserCredentialResponse] = []
    role: str | None = None
    vc_jws: str | None = None


class MembershipResponse(BaseModel):
    user_did: str
    organization_alias: str
    role: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class MembershipCheckResponse(BaseModel):
    member: bool


class CredentialCheckResponse(BaseModel):
    """Does this subject hold a valid credential of this type?

    A boolean and the question it answers — never the credential, its id or its
    dates. The caller is deciding admission, and everything else is disclosure
    it does not need.
    """

    subject_did: str
    credential_type: str
    holds: bool


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
    # No default. It used to default to "verified", which is the exact defect
    # migration 0009 removed from the database — a row reading as verified while
    # nothing verified it. Both constructors pass it today, so the default was
    # unreachable; it was a trap waiting for a third one. Required means a
    # caller that forgets it fails loudly instead of silently reporting an
    # unverified organisation as verified, which is a consent-circle decision.
    status: str
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


class CurrentAgreementResponse(BaseModel):
    """What a participant currently holds — the connector's circle input.

    ``capacity`` is the load-bearing field: ``processor`` means the party acts
    on the controller's instructions and is disclosed rather than asked;
    ``joint_controller`` and ``independent_controller`` both decide their own
    purposes, so they are a new consent question.
    """

    participant_did: str
    owner_alias: str
    agreement_id: str
    version: str | None = None
    capacity: str
    accepted_at: datetime | None = None


class IssuedInviteResponse(BaseModel):
    """Returned once, at issue time. ``code`` is never retrievable again."""

    id: str
    code: str
    label: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class InviteResponse(BaseModel):
    """An invite as an operator sees it later — without the code."""

    id: str
    label: str | None = None
    created_by: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    redeemed_at: datetime | None = None
    application_id: str | None = None


class PublicApplicationResponse(BaseModel):
    """Acknowledgement for the applicant.

    Deliberately minimal: the application is not theirs to read back, and its
    status is an operator's judgement rather than something to poll.
    """

    id: str
    alias: str
    status: str


class SubjectIdentityResponse(BaseModel):
    """A subject DID and the username systems outside the dataspace key on.

    Deliberately does **not** carry the email. The whole point of the DID is to
    keep personal data out of the identifiers that travel, and a resolution
    endpoint that hands back an address defeats it — the username is what the
    receiver needs and nothing more.
    """

    did: str
    username: str
