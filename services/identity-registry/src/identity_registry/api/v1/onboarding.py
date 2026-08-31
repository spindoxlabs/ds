"""Organisation intake — operator-issued invites and the public application route.

An applicant has no identity when it applies; that is what applying is for. So the
intake route cannot use the normal guard, and the alternatives were:

- **fully public** — an unauthenticated write on the service that holds every
  private key, i.e. a spam and enumeration surface;
- **operator-entered only** — cheapest, but then it is not self-service;
- **invite-gated** — the operator is still the gate, the applicant still
  self-serves, and it costs one table. This is what we do.

The code is the only credential the applicant has, so it is treated like one:
generated with `secrets`, stored as a SHA-256 hash, single-use, optionally
expiring, and never readable back.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import EnrolmentToken, OnboardingInvite, OrganizationApplication
from ...dependencies import get_db, require_org_read, require_org_write
from ...schemas.requests import (
    CreateEnrolmentTokenRequest,
    CreateInviteRequest,
    PublicOrganizationApplicationRequest,
)
from ...schemas.responses import (
    EnrolmentTokenResponse,
    InviteResponse,
    IssuedEnrolmentTokenResponse,
    IssuedInviteResponse,
    PublicApplicationResponse,
)
from ...services import enrolment

# Operator-facing: issuing and listing invites.
admin_router = APIRouter(prefix="/admin/onboarding", tags=["onboarding"])

# Applicant-facing: **no scope guard**, gated by the invite code in the body.
# Mounted separately so a scope dependency cannot be added to it by accident when
# the admin router's mount changes.
public_router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _expired(invite: OnboardingInvite, now: datetime) -> bool:
    if invite.expires_at is None:
        return False
    expires = invite.expires_at
    # SQLite drops tzinfo; stored timestamps are UTC by convention.
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= now


@admin_router.post("/invites", status_code=201, response_model=IssuedInviteResponse)
async def create_invite(
    data: CreateInviteRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_org_write),
):
    """Issue a single-use invite code.

    The code is returned **once**. Only its hash is stored, so it cannot be shown
    again — reissue instead, which also invalidates nothing else.
    """
    code = secrets.token_urlsafe(24)
    invite = OnboardingInvite(
        code_hash=_hash(code),
        label=data.label,
        created_by=getattr(principal, "subject", None) or data.created_by,
        expires_at=(
            datetime.now(UTC) + timedelta(days=data.ttl_days) if data.ttl_days else None
        ),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return IssuedInviteResponse(
        id=invite.id,
        code=code,
        label=invite.label,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@admin_router.post(
    "/enrolments", status_code=201, response_model=IssuedEnrolmentTokenResponse
)
async def create_enrolment_token(
    data: CreateEnrolmentTokenRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_org_write),
):
    """Issue the code an admitted organisation enrols its own key with.

    The terminal step of the governance plane, and the *only* thing that used to
    be an act of issuance now is: previously the operator's chain ran
    verify → agreement → **mint a keypair** → promote, and handed over a private
    key the organisation never generated. Now it stops here, and the
    organisation proves control of a key the anchor never sees.

    Returned once. Only its hash is stored, so it cannot be shown again — reissue
    instead, which is also how a leaked code is invalidated.
    """
    try:
        issued = await enrolment.create_enrolment_token(
            db,
            data.owner_alias,
            ttl_days=data.ttl_days,
            label=data.label,
            created_by=getattr(principal, "subject", None),
            roles=data.roles,
            allowed_scopes=data.allowed_scopes,
        )
    except enrolment.EnrolmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public) from exc
    await db.commit()
    return IssuedEnrolmentTokenResponse(
        id=issued.id,
        code=issued.code,
        owner_alias=issued.owner_alias,
        expires_at=issued.expires_at,
    )


@admin_router.get("/enrolments", response_model=list[EnrolmentTokenResponse])
async def list_enrolment_tokens(
    db: AsyncSession = Depends(get_db),
    _principal=Depends(require_org_read),
):
    """Outstanding and spent enrolment codes. Codes are never included.

    `redeemed_did` is the audit trail this list exists for: it is the link from
    an organisation an operator verified to the key that now speaks for it.
    """
    result = await db.execute(
        select(EnrolmentToken).order_by(EnrolmentToken.created_at.desc())
    )
    return [
        EnrolmentTokenResponse(
            id=t.id,
            owner_alias=t.owner_alias,
            label=t.label,
            created_by=t.created_by,
            created_at=t.created_at,
            expires_at=t.expires_at,
            redeemed_at=t.redeemed_at,
            redeemed_did=t.redeemed_did,
        )
        for t in result.scalars().all()
    ]


@admin_router.get("/invites", response_model=list[InviteResponse])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    _principal=Depends(require_org_read),
):
    """Outstanding and spent invites. Codes are never included."""
    result = await db.execute(
        select(OnboardingInvite).order_by(OnboardingInvite.created_at.desc())
    )
    return [
        InviteResponse(
            id=i.id,
            label=i.label,
            created_by=i.created_by,
            created_at=i.created_at,
            expires_at=i.expires_at,
            redeemed_at=i.redeemed_at,
            application_id=i.application_id,
        )
        for i in result.scalars().all()
    ]


@public_router.post(
    "/applications", status_code=201, response_model=PublicApplicationResponse
)
async def submit_application(
    data: PublicOrganizationApplicationRequest,
    db: AsyncSession = Depends(get_db),
):
    """File an organisation application against a valid invite code.

    Deliberately thin. It records a *claim* — nothing here is trusted, and nothing
    it accepts grants anything. Verification is an offline judgement an operator
    makes later, and `evidence_ref` is an external reference (a ticket or document
    id): no documents are uploaded or stored.

    Every rejection answers the same way, so the route cannot be used to probe
    which codes exist.
    """
    invalid = HTTPException(
        status_code=403, detail="Invalid or already used invite code"
    )

    result = await db.execute(
        select(OnboardingInvite).where(
            OnboardingInvite.code_hash == _hash(data.invite_code)
        )
    )
    invite = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if invite is None or invite.redeemed_at is not None or _expired(invite, now):
        raise invalid

    existing = await db.execute(
        select(OrganizationApplication).where(
            OrganizationApplication.alias == data.alias
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail=f"Alias '{data.alias}' is already taken"
        )

    application = OrganizationApplication(
        alias=data.alias,
        legal_name=data.legal_name,
        registration_number=data.registration_number,
        registration_type=data.registration_type,
        hq_country_code=data.hq_country_code,
        legal_country_code=data.legal_country_code,
        roles=data.roles,
        did=data.did,
        dsp_address=data.dsp_address,
        evidence_ref=data.evidence_ref,
        notes=data.notes,
    )
    db.add(application)
    await db.flush()

    invite.redeemed_at = now
    invite.application_id = application.id
    await db.commit()

    # The applicant gets an acknowledgement, not the record: the application is
    # not theirs to read back, and its status is an operator's judgement.
    return PublicApplicationResponse(
        id=application.id,
        alias=application.alias,
        status=application.status,
    )
