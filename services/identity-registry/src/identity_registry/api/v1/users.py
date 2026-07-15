from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Credential, KeycloakMapping
from ...dependencies import get_db, require_resolve_scope
from ...schemas.responses import UserResolveResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/resolve", response_model=UserResolveResponse)
async def resolve_user_by_email(
    email: str = Query(..., description="User email address"),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_resolve_scope),
):
    result = await db.execute(
        select(KeycloakMapping).where(
            func.lower(KeycloakMapping.email) == email.strip().lower()
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="No mapping found for this email")

    cred_result = await db.execute(
        select(Credential)
        .where(
            Credential.subject_did == mapping.did,
            Credential.status == "active",
        )
        .order_by(Credential.issued_at.desc())
        .limit(1)
    )
    credential = cred_result.scalar_one_or_none()

    role = None
    vc_jws = None
    if credential and credential.credential_json:
        cred_json = credential.credential_json
        subject = cred_json.get("credentialSubject") or {}
        role = subject.get("role")
        proof = cred_json.get("proof") or {}
        vc_jws = proof.get("jws")

    return UserResolveResponse(
        did=mapping.did,
        role=role,
        vc_jws=vc_jws,
        subject_id=mapping.subject_id,
    )
