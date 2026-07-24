"""Organisation onboarding operations, shared by the API and the CLI.

Block D §5. The gates (§5.6) are enforced *here*, not in documentation, so the
portal (which calls the HTTP API) and ``ir-cli org`` (which calls the DB
directly) behave identically — the CLI is the reference implementation and both
funnel through these functions.

No PII is stored or emitted: agreement acceptance is proved by ``text_sha256``,
never the prose.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import (
    Agreement,
    AgreementAcceptance,
    Credential,
    Did,
    Key,
    OrganizationApplication,
    Owner,
    Participant,
    StatusList,
)
from .crypto import (
    decrypt_private_jwk,
    encrypt_private_jwk,
    generate_credential_id,
    generate_key_pair,
    hash_sts_secret,
)
from .status_list import create_bitstring, next_available_index, set_bit
from .vc import build_organization_credential, sign_credential


class OrgOnboardingError(Exception):
    """A gate or precondition failed. ``status_code`` maps to the HTTP status
    the API layer should return; the CLI renders ``message`` and exits."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Status-list + trust-anchor helpers ────────────────────────────


async def get_or_create_status_list(db: AsyncSession, list_id: str = "1") -> StatusList:
    result = await db.execute(select(StatusList).where(StatusList.id == list_id))
    sl = result.scalar_one_or_none()
    if not sl:
        sl = StatusList(id=list_id, purpose="revocation", bitstring=create_bitstring())
        db.add(sl)
        await db.flush()
    return sl


async def get_trust_anchor_key(db: AsyncSession, settings: Settings) -> Key:
    ta_did = f"did:web:{settings.trust_anchor_domain}"
    result = await db.execute(
        select(Key).where(Key.owner_did == ta_did, Key.active.is_(True))
    )
    key = result.scalar_one_or_none()
    if not key:
        raise OrgOnboardingError(
            "Trust anchor not bootstrapped. Run: ir-cli bootstrap", status_code=500
        )
    return key


# ── Owner resolution ──────────────────────────────────────────────


async def resolve_owner(db: AsyncSession, alias: str) -> Owner | None:
    result = await db.execute(select(Owner).where(Owner.id == alias))
    owner = result.scalar_one_or_none()
    if owner:
        return owner
    result = await db.execute(select(Owner))
    for o in result.scalars().all():
        if alias in (o.aliases or []):
            return o
    return None


# ── Promotion: application → Owner ────────────────────────────────


async def upsert_owner_from_application(
    db: AsyncSession,
    app: OrganizationApplication,
    *,
    verified_by: str | None = None,
) -> Owner:
    """Promote a verified application's legal identity into an ``Owner`` row.

    Idempotent: re-running updates the existing owner. Sets ``status=verified``.
    """
    now = datetime.now(UTC)
    result = await db.execute(select(Owner).where(Owner.id == app.alias))
    owner = result.scalar_one_or_none()

    if owner is None:
        owner = Owner(id=app.alias, type="schema:Organization", name=app.legal_name)
        db.add(owner)

    owner.name = app.legal_name
    if app.did:
        owner.did = app.did
    owner.registration_number = app.registration_number
    owner.registration_type = app.registration_type
    owner.hq_country_code = app.hq_country_code
    owner.legal_country_code = app.legal_country_code
    owner.parent_organizations = app.parent_organizations
    owner.sub_organizations = app.sub_organizations
    owner.status = "verified"
    owner.verified_at = now
    owner.verified_by = verified_by or app.verified_by
    owner.evidence_ref = app.evidence_ref
    owner.updated_at = now
    await db.flush()
    return owner


# ── Agreement acceptance ──────────────────────────────────────────


async def record_agreement_acceptance(
    db: AsyncSession,
    owner: Owner,
    agreement: Agreement,
    *,
    locale: str,
    accepted_by: str | None = None,
) -> AgreementAcceptance:
    """Record an org's acceptance of an agreement version and stamp the owner's
    current agreement + capacity (§2.5). Idempotent per (owner, agreement, version)."""
    texts = agreement.texts or {}
    if locale not in texts:
        raise OrgOnboardingError(
            f"Agreement {agreement.id}@{agreement.version} has no text for locale "
            f"{locale!r}. Available: {sorted(texts)}",
            status_code=422,
        )
    text_sha256 = texts[locale].get("sha256", "")
    now = datetime.now(UTC)

    result = await db.execute(
        select(AgreementAcceptance).where(
            and_(
                AgreementAcceptance.owner_alias == owner.id,
                AgreementAcceptance.agreement_id == agreement.id,
                AgreementAcceptance.agreement_version == agreement.version,
            )
        )
    )
    acceptance = result.scalar_one_or_none()
    if acceptance is None:
        acceptance = AgreementAcceptance(
            owner_alias=owner.id,
            agreement_id=agreement.id,
            agreement_version=agreement.version,
            capacity=agreement.capacity,
            locale=locale,
            text_sha256=text_sha256,
            accepted_by=accepted_by,
        )
        db.add(acceptance)

    owner.agreement_id = agreement.id
    owner.agreement_version = agreement.version
    owner.agreement_accepted_at = now
    owner.agreement_capacity = agreement.capacity
    owner.updated_at = now
    await db.flush()
    return acceptance


# ── Credential issuance (gated) ───────────────────────────────────


async def issue_organization_credential(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    *,
    roles: list[str],
    allowed_scopes: list[str],
    dsp_address: str | None = None,
    ttl_days: int | None = None,
) -> Credential:
    """Issue an OrganizationCredential for a verified owner.

    Gate (§5.6): ``status == verified`` AND a current agreement version accepted.
    Ensures the owner's ``did:web`` exists as a DID+key so it resolves.
    """
    if owner.status != "verified":
        raise OrgOnboardingError(
            f"Owner {owner.id!r} is {owner.status!r}; must be 'verified' to issue a "
            "credential."
        )
    if not owner.agreement_id:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has not accepted a current agreement version."
        )
    if not owner.did:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has no DID; set one before issuing a credential.",
            status_code=422,
        )

    ta_key = await get_trust_anchor_key(db, settings)
    ta_did = f"did:web:{settings.trust_anchor_domain}"
    status_list_url = f"https://{settings.trust_anchor_domain}/status/1"
    ttl = min(
        ttl_days or settings.default_credential_ttl_days,
        settings.max_credential_ttl_days,
    )

    # Ensure the org DID + key exist (so did:web resolves and the credential is
    # anchored to a registered key), mirroring the data-subject issuance path.
    did_result = await db.execute(select(Did).where(Did.did == owner.did))
    if not did_result.scalar_one_or_none():
        kp = generate_key_pair(owner.did)
        key = Key(
            owner_did=owner.did,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
            public_jwk=kp.public_jwk,
        )
        db.add(key)
        await db.flush()
        endpoints = (
            [{"type": "DSPEndpoint", "serviceEndpoint": dsp_address}]
            if dsp_address
            else None
        )
        db.add(
            Did(
                did=owner.did,
                did_type="participant",
                display_name=owner.name,
                key_id=key.id,
                service_endpoints=endpoints,
            )
        )
        await db.flush()

    sl = await get_or_create_status_list(db)
    sl_index = next_available_index(sl.bitstring)
    cred_id = generate_credential_id()

    vc = build_organization_credential(
        issuer_did=ta_did,
        subject_did=owner.did,
        legal_name=owner.name,
        registration_number=owner.registration_number,
        registration_type=owner.registration_type,
        hq_country_code=owner.hq_country_code,
        legal_country_code=owner.legal_country_code,
        roles=roles,
        allowed_scopes=allowed_scopes,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=status_list_url,
        status_list_index=sl_index,
        parent_organizations=owner.parent_organizations,
        sub_organizations=owner.sub_organizations,
        dsp_address=dsp_address,
        credential_id=cred_id,
        ttl_days=ttl,
    )
    ta_raw_jwk = decrypt_private_jwk(ta_key.private_jwk, settings.encryption_key)
    signed_vc = sign_credential(vc, ta_raw_jwk, ta_key.kid)

    cred = Credential(
        id=cred_id,
        credential_type="OrganizationCredential",
        issuer_did=ta_did,
        subject_did=owner.did,
        credential_json=signed_vc,
        status_list_index=sl_index,
        expires_at=datetime.now(UTC) + timedelta(days=ttl),
    )
    db.add(cred)
    sl.bitstring = set_bit(sl.bitstring, sl_index)
    sl.updated_at = datetime.now(UTC)
    await db.flush()
    return cred


async def _active_org_credential(db: AsyncSession, owner: Owner) -> Credential | None:
    if not owner.did:
        return None
    result = await db.execute(
        select(Credential).where(
            and_(
                Credential.subject_did == owner.did,
                Credential.credential_type == "OrganizationCredential",
                Credential.status == "active",
            )
        )
    )
    return result.scalars().first()


# ── Promotion to participant (gated) ──────────────────────────────


async def promote_owner_to_participant(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    *,
    dsp_address: str,
    roles: list[str],
    allowed_scopes: list[str],
    sts_secret: str = "insecure-dev-secret",
) -> Participant:
    """Register the org as a DSP participant.

    Gate (§5.6): a valid, unrevoked ``OrganizationCredential`` must exist.
    Idempotent: updates the participant if it already exists.
    """
    cred = await _active_org_credential(db, owner)
    if cred is None:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has no active OrganizationCredential; issue one "
            "before promoting to a participant."
        )
    if not owner.did:
        raise OrgOnboardingError(f"Owner {owner.id!r} has no DID.", status_code=422)

    result = await db.execute(select(Participant).where(Participant.did == owner.did))
    participant = result.scalar_one_or_none()
    if participant is None:
        participant = Participant(
            did=owner.did,
            dsp_address=dsp_address,
            roles=roles,
            allowed_scopes=allowed_scopes,
            sts_client_secret=hash_sts_secret(sts_secret),
        )
        db.add(participant)
    else:
        participant.dsp_address = dsp_address
        participant.roles = roles
        participant.allowed_scopes = allowed_scopes
        participant.active = True
        participant.deactivated_at = None
    await db.flush()
    return participant


# ── Suspend / revoke (status + StatusList + deactivate, one tx) ────


async def _revoke_org_credentials(db: AsyncSession, owner: Owner) -> None:
    if not owner.did:
        return
    result = await db.execute(
        select(Credential).where(
            and_(
                Credential.subject_did == owner.did,
                Credential.credential_type == "OrganizationCredential",
                Credential.status == "active",
            )
        )
    )
    now = datetime.now(UTC)
    for cred in result.scalars().all():
        cred.status = "revoked"
        cred.revoked_at = now
        if cred.status_list_index is not None:
            sl = await get_or_create_status_list(db)
            sl.bitstring = set_bit(sl.bitstring, cred.status_list_index)
            sl.updated_at = now


async def suspend_owner(db: AsyncSession, owner: Owner) -> None:
    """Suspend: set the StatusList bit(s) AND deactivate the participant (one tx, §5.6)."""  # noqa: E501
    await _revoke_org_credentials(db, owner)
    owner.status = "suspended"
    owner.updated_at = datetime.now(UTC)
    if owner.did:
        result = await db.execute(
            select(Participant).where(Participant.did == owner.did)
        )
        participant = result.scalar_one_or_none()
        if participant:
            participant.active = False
            participant.deactivated_at = datetime.now(UTC)
    await db.flush()


async def revoke_owner(db: AsyncSession, owner: Owner) -> None:
    """Revoke: same as suspend but terminal."""
    await suspend_owner(db, owner)
    owner.status = "revoked"
    owner.updated_at = datetime.now(UTC)
    await db.flush()
