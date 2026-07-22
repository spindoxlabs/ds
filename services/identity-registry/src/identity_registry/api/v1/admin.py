from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ds_auth import Principal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings, get_settings
from ...db.models import (
    Credential,
    Did,
    Key,
    KeycloakMapping,
    Participant,
    StatusList,
)
from ...dependencies import (
    get_db,
    get_settings_dep,
    require_admin_or_read_scope,
    require_admin_scope,
    require_read_scope,
)
from ...schemas.requests import (
    CreateDidRequest,
    CreateParticipantRequest,
    IssueDataSubjectRequest,
    IssueMembershipRequest,
    KeycloakSyncRequest,
    UpdateParticipantRequest,
)
from ...schemas.responses import (
    CredentialResponse,
    CredentialSummary,
    DataSubjectCredentialResponse,
    DidResponse,
    KeycloakMappingResponse,
    KeyRotationResponse,
    ParticipantCheckResponse,
    ParticipantDetailResponse,
    ParticipantResponse,
)
from ...services.crypto import (
    decrypt_private_jwk,
    encrypt_private_jwk,
    generate_credential_id,
    generate_key_pair,
    next_key_index,
)
from ...services.did import build_did_document
from ...services.status_list import (
    create_bitstring,
    next_available_index,
    set_bit,
)
from ...services.vc import (
    build_data_subject_credential,
    build_membership_credential,
    sign_credential,
)

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_or_create_status_list(
    db: AsyncSession, list_id: str = "1"
) -> StatusList:
    result = await db.execute(select(StatusList).where(StatusList.id == list_id))
    sl = result.scalar_one_or_none()
    if not sl:
        sl = StatusList(
            id=list_id,
            purpose="revocation",
            bitstring=create_bitstring(),
        )
        db.add(sl)
        await db.flush()
    return sl


async def _get_trust_anchor_key(db: AsyncSession, settings: Settings) -> Key:
    trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"
    result = await db.execute(
        select(Key).where(Key.owner_did == trust_anchor_did, Key.active.is_(True))
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(
            status_code=500,
            detail="Trust anchor not bootstrapped. Run: ir-cli bootstrap",
        )
    return key


# ── Participants ──────────────────────────────────────────────────


@router.post("/participants", status_code=201, response_model=ParticipantResponse)
async def create_participant(
    data: CreateParticipantRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    existing = await db.execute(
        select(Participant).where(Participant.did == data.did)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Participant already exists")

    did_result = await db.execute(select(Did).where(Did.did == data.did))
    did_record = did_result.scalar_one_or_none()

    if not did_record:
        kp = generate_key_pair(data.did)
        key = Key(
            owner_did=data.did,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
            public_jwk=kp.public_jwk,
        )
        db.add(key)
        await db.flush()

        did_record = Did(
            did=data.did,
            did_type="participant",
            key_id=key.id,
            service_endpoints=(
                [{"type": "DSPEndpoint", "serviceEndpoint": data.dsp_address}]
                if data.dsp_address
                else None
            ),
        )
        db.add(did_record)
        await db.flush()

    participant = Participant(
        did=data.did,
        dsp_address=data.dsp_address,
        roles=data.roles,
        allowed_scopes=data.allowed_scopes,
    )
    db.add(participant)
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


@router.get("/participants", response_model=list[ParticipantResponse])
async def list_participants(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_admin_or_read_scope),
    settings: Settings = Depends(get_settings_dep),
):
    has_admin = principal.grants(settings.admin_scope)

    stmt = select(Participant)
    if active_only or not has_admin:
        stmt = stmt.where(Participant.active.is_(True))

    result = await db.execute(stmt)
    participants = result.scalars().all()
    return [
        ParticipantResponse(
            did=p.did,
            dsp_address=p.dsp_address,
            roles=p.roles,
            allowed_scopes=p.allowed_scopes,
            active=p.active,
            registered_at=p.registered_at,
        )
        for p in participants
    ]


@router.get(
    "/participants/check",
    response_model=ParticipantCheckResponse,
)
async def check_participant(
    did: str = Query(...),
    scope: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    result = await db.execute(
        select(Participant).where(Participant.did == did, Participant.active.is_(True))
    )
    participant = result.scalar_one_or_none()
    if not participant:
        return ParticipantCheckResponse(allowed=False)

    allowed = scope in participant.allowed_scopes
    return ParticipantCheckResponse(allowed=allowed)


@router.get("/participants/{did:path}", response_model=ParticipantDetailResponse)
async def get_participant(
    did: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Participant).where(Participant.did == did))
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    cred_result = await db.execute(
        select(Credential).where(Credential.subject_did == did)
    )
    creds = cred_result.scalars().all()

    return ParticipantDetailResponse(
        did=participant.did,
        dsp_address=participant.dsp_address,
        roles=participant.roles,
        allowed_scopes=participant.allowed_scopes,
        active=participant.active,
        registered_at=participant.registered_at,
        credentials=[
            CredentialSummary(
                id=c.id,
                credential_type=c.credential_type,
                status=c.status,
                issued_at=c.issued_at,
                expires_at=c.expires_at,
            )
            for c in creds
        ],
    )


@router.patch("/participants/{did:path}", response_model=ParticipantResponse)
async def update_participant(
    did: str,
    data: UpdateParticipantRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Participant).where(Participant.did == did))
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    if data.dsp_address is not None:
        participant.dsp_address = data.dsp_address
    if data.roles is not None:
        participant.roles = data.roles
    if data.allowed_scopes is not None:
        participant.allowed_scopes = data.allowed_scopes
    if data.active is not None:
        participant.active = data.active
        if not data.active:
            participant.deactivated_at = datetime.now(UTC)

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


@router.delete("/participants/{did:path}", status_code=204)
async def delete_participant(
    did: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Participant).where(Participant.did == did))
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    participant.active = False
    participant.deactivated_at = datetime.now(UTC)

    cred_result = await db.execute(
        select(Credential).where(
            Credential.subject_did == did,
            Credential.status == "active",
        )
    )
    for cred in cred_result.scalars().all():
        cred.status = "revoked"
        cred.revoked_at = datetime.now(UTC)
        if cred.status_list_index is not None:
            sl = await _get_or_create_status_list(db)
            sl.bitstring = set_bit(sl.bitstring, cred.status_list_index)
            sl.updated_at = datetime.now(UTC)

    await db.commit()


# ── DIDs ──────────────────────────────────────────────────────────


@router.post("/dids", status_code=201, response_model=DidResponse)
async def create_did(
    data: CreateDidRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    existing = await db.execute(select(Did).where(Did.did == data.did))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="DID already exists")

    kp = generate_key_pair(data.did)
    key = Key(
        owner_did=data.did,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
        public_jwk=kp.public_jwk,
    )
    db.add(key)
    await db.flush()

    did_record = Did(
        did=data.did,
        did_type=data.did_type,
        display_name=data.display_name,
        service_endpoints=data.service_endpoints,
        key_id=key.id,
    )
    db.add(did_record)
    await db.commit()

    await db.refresh(did_record)
    await db.refresh(key)

    did_doc = build_did_document(
        did=data.did,
        public_jwk=kp.public_jwk,
        did_type=data.did_type,
        service_endpoints=data.service_endpoints,
    )

    return DidResponse(
        did=did_record.did,
        did_type=did_record.did_type,
        active=did_record.active,
        created_at=did_record.created_at,
        key={"kid": key.kid, "public_jwk": key.public_jwk},
        did_document=did_doc,
    )


@router.get("/dids/{did:path}", response_model=DidResponse)
async def get_did(
    did: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Did).where(Did.did == did))
    did_record = result.scalar_one_or_none()
    if not did_record:
        raise HTTPException(status_code=404, detail="DID not found")

    key_info = None
    if did_record.key:
        key_info = {
            "kid": did_record.key.kid,
            "public_jwk": did_record.key.public_jwk,
        }

    return DidResponse(
        did=did_record.did,
        did_type=did_record.did_type,
        active=did_record.active,
        created_at=did_record.created_at,
        key=key_info,
    )


@router.delete("/dids/{did:path}", status_code=204)
async def delete_did(
    did: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Did).where(Did.did == did))
    did_record = result.scalar_one_or_none()
    if not did_record:
        raise HTTPException(status_code=404, detail="DID not found")

    did_record.active = False
    did_record.deactivated_at = datetime.now(UTC)

    cred_result = await db.execute(
        select(Credential).where(
            Credential.subject_did == did,
            Credential.status == "active",
        )
    )
    for cred in cred_result.scalars().all():
        cred.status = "revoked"
        cred.revoked_at = datetime.now(UTC)
        if cred.status_list_index is not None:
            sl = await _get_or_create_status_list(db)
            sl.bitstring = set_bit(sl.bitstring, cred.status_list_index)
            sl.updated_at = datetime.now(UTC)

    await db.commit()


# ── Credentials ───────────────────────────────────────────────────


@router.post(
    "/credentials/membership", status_code=201, response_model=CredentialResponse
)
async def issue_membership_credential(
    data: IssueMembershipRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    did_result = await db.execute(
        select(Did).where(Did.did == data.subject_did, Did.active.is_(True))
    )
    if not did_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Subject DID not found or inactive")

    trust_anchor_key = await _get_trust_anchor_key(db, settings)
    trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"
    status_list_url = f"https://{settings.trust_anchor_domain}/status/1"

    ttl = min(
        data.ttl_days or settings.default_credential_ttl_days,
        settings.max_credential_ttl_days,
    )

    sl = await _get_or_create_status_list(db)
    sl_index = next_available_index(sl.bitstring)

    cred_id = generate_credential_id()
    vc = build_membership_credential(
        issuer_did=trust_anchor_did,
        subject_did=data.subject_did,
        role=data.role,
        allowed_scopes=data.allowed_scopes,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=status_list_url,
        status_list_index=sl_index,
        credential_id=cred_id,
        ttl_days=ttl,
    )

    ta_raw_jwk = decrypt_private_jwk(trust_anchor_key.private_jwk, settings.encryption_key)
    signed_vc = sign_credential(vc, ta_raw_jwk, trust_anchor_key.kid)

    cred = Credential(
        id=cred_id,
        credential_type="MembershipCredential",
        issuer_did=trust_anchor_did,
        subject_did=data.subject_did,
        credential_json=signed_vc,
        status_list_index=sl_index,
        expires_at=datetime.now(UTC) + timedelta(days=ttl),
    )
    db.add(cred)

    await db.commit()
    await db.refresh(cred)
    return CredentialResponse(
        credentialId=cred.id,
        subjectDid=cred.subject_did,
        issuedAt=cred.issued_at,
        expiresAt=cred.expires_at,
    )


@router.post(
    "/credentials/data-subject",
    status_code=201,
    response_model=DataSubjectCredentialResponse,
)
async def issue_data_subject_credential(
    data: IssueDataSubjectRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    trust_anchor_key = await _get_trust_anchor_key(db, settings)
    trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"
    users_domain = settings.trust_anchor_domain.replace("trust-anchor.", "users.")
    subject_did = f"did:web:{users_domain}:{data.subject_id}"

    did_result = await db.execute(select(Did).where(Did.did == subject_did))
    did_record = did_result.scalar_one_or_none()

    status_list_url = f"https://{settings.trust_anchor_domain}/status/1"

    ttl = min(
        data.ttl_days or settings.default_credential_ttl_days,
        settings.max_credential_ttl_days,
    )

    if not did_record:
        kp = generate_key_pair(subject_did)
        key = Key(
            owner_did=subject_did,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
            public_jwk=kp.public_jwk,
        )
        db.add(key)
        await db.flush()

        did_record = Did(
            did=subject_did,
            did_type="user",
            key_id=key.id,
        )
        db.add(did_record)
        await db.flush()

    sl = await _get_or_create_status_list(db)
    sl_index = next_available_index(sl.bitstring)

    cred_id = generate_credential_id()
    vc = build_data_subject_credential(
        issuer_did=trust_anchor_did,
        subject_did=subject_did,
        role=data.role,
        linked_participant_did=data.linked_participant_did,
        allowed_actions=data.allowed_actions,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=status_list_url,
        status_list_index=sl_index,
        credential_id=cred_id,
        ttl_days=ttl,
    )

    ta_raw_jwk = decrypt_private_jwk(trust_anchor_key.private_jwk, settings.encryption_key)
    signed_vc = sign_credential(vc, ta_raw_jwk, trust_anchor_key.kid)

    cred = Credential(
        id=cred_id,
        credential_type="DataSubjectCredential",
        issuer_did=trust_anchor_did,
        subject_did=subject_did,
        credential_json=signed_vc,
        status_list_index=sl_index,
        expires_at=datetime.now(UTC) + timedelta(days=ttl),
    )
    db.add(cred)
    await db.commit()

    await db.refresh(cred)
    return DataSubjectCredentialResponse(
        subjectDid=subject_did,
        credentialId=cred.id,
        generatedAt=cred.issued_at,
    )


@router.get("/credentials/{cred_id}")
async def get_credential(
    cred_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Credential).where(Credential.id == cred_id))
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    return cred.credential_json


@router.get("/credentials", response_model=list[CredentialSummary])
async def list_credentials(
    subject_did: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    stmt = select(Credential)
    if subject_did:
        stmt = stmt.where(Credential.subject_did == subject_did)

    result = await db.execute(stmt)
    creds = result.scalars().all()
    return [
        CredentialSummary(
            id=c.id,
            credential_type=c.credential_type,
            status=c.status,
            issued_at=c.issued_at,
            expires_at=c.expires_at,
        )
        for c in creds
    ]


@router.delete("/credentials/{cred_id}", status_code=204)
async def revoke_credential(
    cred_id: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(select(Credential).where(Credential.id == cred_id))
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    cred.status = "revoked"
    cred.revoked_at = datetime.now(UTC)

    if cred.status_list_index is not None:
        sl = await _get_or_create_status_list(db)
        sl.bitstring = set_bit(sl.bitstring, cred.status_list_index)
        sl.updated_at = datetime.now(UTC)

    await db.commit()


# ── Keycloak sync ─────────────────────────────────────────────────


@router.post("/keycloak/sync", status_code=200)
async def keycloak_sync(
    data: KeycloakSyncRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    did_result = await db.execute(select(Did).where(Did.did == data.did))
    did_record = did_result.scalar_one_or_none()
    if not did_record:
        raise HTTPException(status_code=404, detail="DID not found")

    if not data.did.startswith("did:web:"):
        raise HTTPException(status_code=400, detail="Invalid DID format")

    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.did == data.did)
    )
    mapping = result.scalar_one_or_none()

    if mapping:
        mapping.keycloak_realm = data.keycloak_realm
        mapping.keycloak_user_id = data.keycloak_user_id
        mapping.email = data.email
        mapping.subject_id = data.did
        mapping.synced_at = datetime.now(UTC)
    else:
        mapping = KeycloakMapping(
            did=data.did,
            keycloak_realm=data.keycloak_realm,
            keycloak_user_id=data.keycloak_user_id,
            email=data.email,
            subject_id=data.did,
        )
        db.add(mapping)

    await db.commit()

    if settings.keycloak_admin_url:
        import httpx

        kc_url = (
            f"{settings.keycloak_admin_url}/admin/realms/{data.keycloak_realm}"
            f"/users/{data.keycloak_user_id}"
        )
        try:
            token_url = (
                f"{settings.keycloak_admin_url}/realms/{data.keycloak_realm}"
                f"/protocol/openid-connect/token"
            )
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.keycloak_client_id,
                        "client_secret": settings.keycloak_client_secret,
                    },
                )
                token_resp.raise_for_status()
                kc_token = token_resp.json()["access_token"]

                resp = await client.put(
                    kc_url,
                    json={"attributes": {"dataspace_did": [data.did]}},
                    headers={"Authorization": f"Bearer {kc_token}"},
                )
                resp.raise_for_status()
        except httpx.HTTPError:
            pass

    return {"status": "synced", "did": data.did}


# ── Keys ──────────────────────────────────────────────────────────


@router.post(
    "/keys/rotate/{did:path}",
    status_code=200,
    response_model=KeyRotationResponse,
)
async def rotate_key(
    did: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_admin_scope),
):
    did_result = await db.execute(select(Did).where(Did.did == did))
    did_record = did_result.scalar_one_or_none()
    if not did_record:
        raise HTTPException(status_code=404, detail="DID not found")

    old_key_result = await db.execute(
        select(Key).where(Key.owner_did == did, Key.active.is_(True))
    )
    old_key = old_key_result.scalar_one_or_none()
    if not old_key:
        raise HTTPException(status_code=404, detail="No active key for DID")

    new_index = next_key_index(old_key.kid)

    old_key.active = False
    old_key.rotated_at = datetime.now(UTC)

    kp = generate_key_pair(did, key_index=new_index)
    new_key = Key(
        owner_did=did,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
        public_jwk=kp.public_jwk,
    )
    db.add(new_key)
    await db.flush()

    did_record.key_id = new_key.id

    await db.commit()
    return KeyRotationResponse(new_kid=kp.kid, old_kid=old_key.kid)


# ── Keycloak mapping ─────────────────────────────────────────────


@router.get(
    "/keycloak/mapping/{did:path}",
    response_model=KeycloakMappingResponse,
)
async def get_keycloak_mapping_by_did(
    did: str,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.did == did)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return KeycloakMappingResponse(
        did=mapping.did,
        keycloak_realm=mapping.keycloak_realm,
        keycloak_user_id=mapping.keycloak_user_id,
        email=mapping.email,
        subject_id=mapping.subject_id,
    )


@router.get(
    "/keycloak/mapping",
    response_model=KeycloakMappingResponse,
)
async def get_keycloak_mapping_by_subject(
    subject_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_scope),
):
    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.subject_id == subject_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return KeycloakMappingResponse(
        did=mapping.did,
        keycloak_realm=mapping.keycloak_realm,
        keycloak_user_id=mapping.keycloak_user_id,
        email=mapping.email,
        subject_id=mapping.subject_id,
    )
