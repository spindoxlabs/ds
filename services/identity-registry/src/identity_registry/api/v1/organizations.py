from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import Agreement, OrganizationApplication, Owner
from ...dependencies import (
    get_db,
    get_settings_dep,
    require_org_promote,
    require_org_read,
    require_org_write,
)
from ...schemas.requests import (
    AcceptAgreementRequest,
    AddTrustedIssuerRequest,
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
from ...services import trust_list
from ...services.enrolment import EnrolmentError
from ...services.registry_notify import invalidate_participant_caches
from ...services import provisioning
from ...services.keycloak_admin import KeycloakAdminClient

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
    response: Response,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_org_write),
):
    """Register an organisation application. **Upsert by alias.**

    An alias identifies one organisation, so re-registering it is the same
    application — this used to insert another row per POST, leaving several
    live applications for a single organisation and giving whichever query ran
    first a different answer about its state. `ir-cli org register` has always
    resolved by alias; both now come through `ops.upsert_application`, so the
    CLI and HTTP paths cannot disagree about what a re-registration means.

    201 on create, 200 on update. Verification state is never written here, and
    editing a *verified* application's legal identity is a 409 — the issued
    credential asserts the old value, so that is a re-verification.

    The public invite-gated intake (`POST /onboarding/applications`) keeps its
    409 instead: a stranger holding an invite must not be able to mutate an
    organisation that already exists.
    """
    # Only what the caller actually sent. An omitted optional field used to mean
    # "set to None", which on a re-registration silently wiped values the caller
    # never mentioned — and would fire the verified-lock below on fields nobody
    # touched. A file (`org import`/`apply`) is a full desired state; a call is
    # a patch of what it names.
    def _clean(payload: dict) -> dict:
        out = {k: v for k, v in payload.items() if k != "alias"}
        for key in ("parent_organizations", "sub_organizations"):
            if key in out:
                out[key] = out[key] or None
        return out

    try:
        app, created = await ops.upsert_application(
            db,
            data.alias,
            _clean(data.model_dump(exclude_unset=True)),
            # A partial body must still create a complete row, so the model's
            # own defaults (`roles: [consumer]`) apply on create only.
            defaults=_clean(data.model_dump()),
        )
    except ops.OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    await db.commit()
    await db.refresh(app)
    response.status_code = 201 if created else 200
    return _app_to_response(app)


@router.get(
    "/organizations/applications",
    response_model=list[OrganizationApplicationResponse],
)
async def list_applications(
    status: str | None = Query(default=None),
    alias: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_org_read),
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
    _claims: dict = Depends(require_org_read),
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
    _claims: dict = Depends(require_org_write),
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
    _claims: dict = Depends(require_org_write),
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
    _claims: dict = Depends(require_org_write),
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
    # the register bits + participant activation happen atomically (§5.6).
    # `verified` is two different transitions depending on where it comes from:
    # from `suspended` it is a reinstatement and must clear what suspension set,
    # which is why it cannot be an assignment.
    try:
        if new_status == "suspended":
            await ops.suspend_owner(db, owner)
        elif new_status == "revoked":
            await ops.revoke_owner(db, owner)
        elif new_status == "verified":
            if owner.status == "suspended":
                await ops.reinstate_owner(db, owner)
            else:
                owner.status = "verified"
                if owner.verified_at is None:
                    owner.verified_at = datetime.now(UTC)
        elif new_status is not None:
            owner.status = new_status
    except ops.OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

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
    _claims: dict = Depends(require_org_promote),
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
        )
    except ops.OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    await db.commit()
    await db.refresh(participant)

    # The registry just changed. Connectors cache it for a minute, which is
    # right for per-negotiation membership checks and wrong for an operator
    # staring at a list that should already contain this participant.
    await invalidate_participant_caches(settings)

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
    _claims: dict = Depends(require_org_write),
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


@router.post(
    "/owners/{alias}/provisioning-bundle",
    status_code=201,
)
async def generate_provisioning_bundle(
    alias: str,
    format: Literal["json", "env", "properties", "all"] = "json",
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_org_promote),
):
    """Everything a verified organisation needs to stand up its own ds deployment.

    **It no longer hands over an identity** (`DID-10`). It used to return an STS
    client secret this registry had minted, with `sts_token_url` and
    `credential_service_url` pointing at **the anchor** — so the artefact an
    operator sent a third party configured that third party to use somebody
    else's registry as its own Secure Token Service and credential store.

    What it returns now: trust material, the counterparties, and a **single-use
    enrolment code**. The recipient generates its own key, publishes its own DID
    document, and proves control of it. The two secrets it needs are *named* in
    the rendered config and left empty, because they are its to choose.

    **Nothing rotates any more**, and the reason it used to is gone with it: the
    rotation protected a secret only this registry could mint. Asking twice no
    longer kills the first copy — though each call does issue a *new* enrolment
    code, and a code is single-use.

    Gated on `organizations.promote` rather than `.write`: admitting a DSP
    counterparty is the same class of act as creating one.

    `format=env|properties` renders the config files directly, using the same
    renderers as `ir-cli org bundle` so the two cannot drift. `format=all`
    returns the bundle *and* both renderings together. An unknown format is a
    422, not a silent fall-back to JSON — a typo that quietly returns a different
    artefact than the one asked for is how a `.properties` file ends up holding a
    secret.
    """
    owner = await ops.resolve_owner(db, alias)
    if not owner:
        raise HTTPException(status_code=404, detail=f"Owner not found: {alias}")

    keycloak_client_id = None
    keycloak_secret = None
    if (
        settings.keycloak_mutate
        and settings.keycloak_admin_url
        and settings.keycloak_admin_user
    ):
        # A third party's connector authenticates service-to-service against this
        # realm, so its client lives here. Failing to provision it would hand over
        # a bundle that cannot actually talk to the registry.
        #
        # Unconfigured admin credentials are not an error: the bundle is still
        # useful without them, and a deployment may provision clients elsewhere.
        # `keycloak_mutate=false` says the same thing deliberately — ds is a guest
        # in this realm and creating clients in it is not ds's to do.
        client = await KeycloakAdminClient.authenticate(
            settings.keycloak_admin_url,
            settings.keycloak_realm,
            admin_user=settings.keycloak_admin_user,
            admin_password=settings.keycloak_admin_password or "",
        )
        try:
            keycloak_client_id = provisioning.client_id_for(alias)
            keycloak_secret = await client.ensure_service_client(
                keycloak_client_id,
                name=f"ds connector — {owner.name or alias}",
                scopes=provisioning.CONNECTOR_SCOPES,
                audiences=provisioning.CONNECTOR_AUDIENCES,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the operator
            raise HTTPException(
                status_code=502,
                detail=f"Could not provision a Keycloak client for {alias}: {exc}",
            ) from exc
        finally:
            await client.aclose()

    try:
        bundle = await provisioning.build_bundle(
            db,
            settings,
            owner,
            keycloak_client_id=keycloak_client_id,
            keycloak_client_secret=keycloak_secret,
        )
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except EnrolmentError as exc:
        # The bundle carries a single-use enrolment code, so building one goes
        # through the same gate as issuing one: only a **verified** organisation
        # may be handed a code. That refusal reached the operator as a **500** —
        # a server error for a decision the server made deliberately, with the
        # reason sitting in a log nobody was reading.
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    await db.commit()

    if format == "env":
        return PlainTextResponse(provisioning.render_env(bundle), status_code=201)
    if format == "properties":
        return PlainTextResponse(
            provisioning.render_properties(bundle), status_code=201
        )
    if format == "all":
        return {
            "bundle": bundle,
            "env": provisioning.render_env(bundle),
            "properties": provisioning.render_properties(bundle),
        }
    return bundle


# ── Trust list (`DSSC-TRF-05`, `-17`) ─────────────────────────────


@router.post("/trust/issuers", status_code=201)
async def add_trusted_issuer(
    data: AddTrustedIssuerRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_org_promote),
):
    """Accredit an entity to attest, within a named scope.

    Gated on `organizations.promote`, the same grant as admitting a participant:
    saying "this dataspace stands behind that entity's attestations" is at least
    as consequential as admitting a counterparty, and more so than editing an
    application.
    """
    try:
        entry = await trust_list.add_issuer(
            db,
            did=data.did,
            name=data.name,
            role=data.role,
            scope_of_attestation=data.scope_of_attestation,
            derives_authority_from=data.derives_authority_from,
            added_by=getattr(principal, "subject", None),
        )
    except trust_list.TrustListError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    await db.commit()
    return {"did": entry.did, "status": entry.status}


@router.delete("/trust/issuers/{did:path}", status_code=200)
async def revoke_trusted_issuer(
    did: str,
    reason: str = Query(..., min_length=3),
    db: AsyncSession = Depends(get_db),
    _principal=Depends(require_org_promote),
):
    """Withdraw accreditation. The entry **stays listed**, marked revoked.

    `DSSC-TRF-05` requires revoked entries in the listing, and the reason is
    required rather than optional: a verifier holding credentials from this
    issuer needs to know whether what it already accepted is still good, and
    "removed, no reason given" answers nothing.
    """
    try:
        entry = await trust_list.revoke_issuer(db, did, reason=reason)
    except trust_list.TrustListError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    await db.commit()
    return {"did": entry.did, "status": entry.status, "reason": entry.revocation_reason}
