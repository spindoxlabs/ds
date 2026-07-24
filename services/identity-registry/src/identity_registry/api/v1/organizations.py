from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import Agreement, OrganizationApplication, Owner
from ...dependencies import get_db, get_settings_dep, require_admin_scope
from ...schemas.requests import (
    AcceptAgreementRequest,
    CreateOrganizationApplicationRequest,
    IssueOrganizationCredentialRequest,
    PatchOwnerRequest,
    PromoteOwnerRequest,
    UpdateOrganizationApplicationRequest,
)
from ...schemas.responses import (
    AgreementAcceptanceResponse,
    CredentialResponse,
    OrganizationApplicationResponse,
    OwnerResponse,
    ParticipantResponse,
)
from ...services import org_onboarding as ops

router = APIRouter(prefix="/admin", tags=["organizations"])


def _app_to_response(app: OrganizationApplication) -> OrganizationApplicationResponse:
    return OrganizationApplicationResponse(
        id=app.id,
        alias=app.alias,
        legal_name=app.legal_name,
        registration_number=app.registration_number,
        registration_type=app.registration_type,
        hq_country_code=app.hq_country_code,
        legal_country_code=app.legal_country_code,
        parent_organizations=app.parent_organizations,
        sub_organizations=app.sub_organizations,
        roles=app.roles,
        did=app.did,
        dsp_address=app.dsp_address,
        status=app.status,
        evidence_ref=app.evidence_ref,
        verified_by=app.verified_by,
        verified_at=app.verified_at,
        notes=app.notes,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def _owner_to_response(owner: Owner) -> OwnerResponse:
    return OwnerResponse(
        id=owner.id,
        type=owner.type,
        name=owner.name,
        did=owner.did,
        url=owner.url,
        aliases=owner.aliases or [],
        organization_config=owner.organization_config,
        canonical_uri=owner.did or owner.url or None,
        registration_number=owner.registration_number,
        registration_type=owner.registration_type,
        hq_country_code=owner.hq_country_code,
        legal_country_code=owner.legal_country_code,
        parent_organizations=owner.parent_organizations,
        sub_organizations=owner.sub_organizations,
        status=owner.status,
        verified_at=owner.verified_at,
        verified_by=owner.verified_by,
        evidence_ref=owner.evidence_ref,
        agreement_id=owner.agreement_id,
        agreement_version=owner.agreement_version,
        agreement_accepted_at=owner.agreement_accepted_at,
        agreement_capacity=owner.agreement_capacity,
        created_at=owner.created_at,
        updated_at=owner.updated_at,
    )


# ── Organisation applications ─────────────────────────────────────


@router.post(
    "/organizations/applications",
    status_code=201,
    response_model=OrganizationApplicationResponse,
)
async def create_application(
    data: CreateOrganizationApplicationRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    app = OrganizationApplication(
        alias=data.alias,
        legal_name=data.legal_name,
        registration_number=data.registration_number,
        registration_type=data.registration_type,
        hq_country_code=data.hq_country_code,
        legal_country_code=data.legal_country_code,
        parent_organizations=data.parent_organizations or None,
        sub_organizations=data.sub_organizations or None,
        roles=data.roles,
        did=data.did,
        dsp_address=data.dsp_address,
        notes=data.notes,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.get(
    "/organizations/applications",
    response_model=list[OrganizationApplicationResponse],
)
async def list_applications(
    status: str | None = Query(default=None),
    alias: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    stmt = select(OrganizationApplication)
    if status:
        stmt = stmt.where(OrganizationApplication.status == status)
    if alias:
        stmt = stmt.where(OrganizationApplication.alias == alias)
    result = await db.execute(stmt)
    return [_app_to_response(a) for a in result.scalars().all()]


@router.get(
    "/organizations/applications/{application_id}",
    response_model=OrganizationApplicationResponse,
)
async def get_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(OrganizationApplication).where(
            OrganizationApplication.id == application_id
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _app_to_response(app)


@router.patch(
    "/organizations/applications/{application_id}",
    response_model=OrganizationApplicationResponse,
)
async def update_application(
    application_id: str,
    data: UpdateOrganizationApplicationRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(OrganizationApplication).where(
            OrganizationApplication.id == application_id
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    fields = data.model_dump(exclude_unset=True)
    verifying = fields.get("status") == "verified" and app.status != "verified"

    for key in (
        "legal_name",
        "registration_number",
        "registration_type",
        "hq_country_code",
        "legal_country_code",
        "roles",
        "did",
        "dsp_address",
        "status",
        "evidence_ref",
        "verified_by",
        "notes",
    ):
        if key in fields:
            setattr(app, key, fields[key])
    if "parent_organizations" in fields:
        app.parent_organizations = fields["parent_organizations"] or None
    if "sub_organizations" in fields:
        app.sub_organizations = fields["sub_organizations"] or None

    if verifying:
        if not app.verified_by:
            raise HTTPException(
                status_code=422,
                detail="verified_by is required to mark an application verified",
            )
        app.verified_at = datetime.now(UTC)
        # Promote the legal identity into an Owner row on verification (§5.5).
        await ops.upsert_owner_from_application(db, app, verified_by=app.verified_by)

    app.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


# ── Organisation credential ───────────────────────────────────────


@router.post(
    "/credentials/organization",
    status_code=201,
    response_model=CredentialResponse,
)
async def issue_organization_credential(
    data: IssueOrganizationCredentialRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    owner = await ops.resolve_owner(db, data.alias)
    if not owner:
        raise HTTPException(status_code=404, detail=f"Owner not found: {data.alias}")

    try:
        cred = await ops.issue_organization_credential(
            db,
            settings,
            owner,
            roles=data.roles or ["consumer"],
            allowed_scopes=data.allowed_scopes or ["dataspaces.query"],
            dsp_address=data.dsp_address,
            ttl_days=data.ttl_days,
        )
    except ops.OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    await db.commit()
    await db.refresh(cred)
    return CredentialResponse(
        credentialId=cred.id,
        subjectDid=cred.subject_did,
        issuedAt=cred.issued_at,
        expiresAt=cred.expires_at,
    )


# ── Owner promotion / lifecycle ───────────────────────────────────


@router.patch("/owners/{alias}", response_model=OwnerResponse)
async def patch_owner(
    alias: str,
    data: PatchOwnerRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    owner = await ops.resolve_owner(db, alias)
    if not owner:
        raise HTTPException(status_code=404, detail=f"Owner not found: {alias}")

    fields = data.model_dump(exclude_unset=True)
    new_status = fields.get("status")

    for key in (
        "name",
        "did",
        "url",
        "registration_number",
        "registration_type",
        "hq_country_code",
        "legal_country_code",
        "parent_organizations",
        "sub_organizations",
        "evidence_ref",
        "verified_by",
    ):
        if key in fields:
            setattr(owner, key, fields[key])

    # Status transitions with side effects go through the shared, gated ops so
    # the StatusList bit + participant deactivation happen atomically (§5.6).
    if new_status == "suspended":
        await ops.suspend_owner(db, owner)
    elif new_status == "revoked":
        await ops.revoke_owner(db, owner)
    elif new_status == "verified":
        owner.status = "verified"
        if owner.verified_at is None:
            owner.verified_at = datetime.now(UTC)
    elif new_status is not None:
        owner.status = new_status

    owner.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(owner)
    return _owner_to_response(owner)


@router.post(
    "/owners/{alias}/promote",
    status_code=201,
    response_model=ParticipantResponse,
)
async def promote_owner(
    alias: str,
    data: PromoteOwnerRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    owner = await ops.resolve_owner(db, alias)
    if not owner:
        raise HTTPException(status_code=404, detail=f"Owner not found: {alias}")

    try:
        participant = await ops.promote_owner_to_participant(
            db,
            settings,
            owner,
            dsp_address=data.dsp_address,
            roles=data.roles or ["consumer"],
            allowed_scopes=data.allowed_scopes,
            sts_secret=data.sts_secret,
        )
    except ops.OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    await db.commit()
    await db.refresh(participant)
    return ParticipantResponse(
        did=participant.did,
        dsp_address=participant.dsp_address,
        roles=participant.roles,
        allowed_scopes=participant.allowed_scopes,
        active=participant.active,
        registered_at=participant.registered_at,
    )


@router.post(
    "/owners/{alias}/agreement",
    status_code=201,
    response_model=AgreementAcceptanceResponse,
)
async def accept_agreement(
    alias: str,
    data: AcceptAgreementRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    owner = await ops.resolve_owner(db, alias)
    if not owner:
        raise HTTPException(status_code=404, detail=f"Owner not found: {alias}")

    result = await db.execute(
        select(Agreement).where(
            Agreement.id == data.agreement_id, Agreement.version == data.version
        )
    )
    agreement = result.scalar_one_or_none()
    if not agreement:
        raise HTTPException(
            status_code=404,
            detail=f"Agreement not found: {data.agreement_id}@{data.version}",
        )

    try:
        acceptance = await ops.record_agreement_acceptance(
            db, owner, agreement, locale=data.locale, accepted_by=data.accepted_by
        )
    except ops.OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    await db.commit()
    await db.refresh(acceptance)
    return AgreementAcceptanceResponse(
        id=acceptance.id,
        owner_alias=acceptance.owner_alias,
        agreement_id=acceptance.agreement_id,
        agreement_version=acceptance.agreement_version,
        capacity=acceptance.capacity,
        locale=acceptance.locale,
        text_sha256=acceptance.text_sha256,
        accepted_by=acceptance.accepted_by,
        accepted_at=acceptance.accepted_at,
    )
