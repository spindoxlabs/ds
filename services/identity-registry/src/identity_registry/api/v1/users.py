from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Credential, KeycloakMapping
from ...dependencies import get_db, require_resolve_scope
from ...schemas.responses import UserCredentialResponse, UserResolveResponse

router = APIRouter(prefix="/users", tags=["users"])


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """Whether a credential is past its expiry.

    ``DateTime(timezone=True)`` only round-trips tzinfo on PostgreSQL; SQLite
    hands back a naive value, so comparing it directly raises. Stored timestamps
    are UTC by convention, so a naive one is read as UTC — the same
    normalisation `connector/services/pending_sweep.py` does.
    """
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _to_credential_response(credential: Credential) -> UserCredentialResponse:
    cred_json = credential.credential_json or {}
    subject = cred_json.get("credentialSubject") or {}
    proof = cred_json.get("proof") or {}
    return UserCredentialResponse(
        role=subject.get("role"),
        vc_jws=proof.get("jws"),
        credential_type=credential.credential_type,
        issued_at=credential.issued_at,
        expires_at=credential.expires_at,
    )


@router.get("/resolve", response_model=UserResolveResponse)
async def resolve_user_by_email(
    email: str = Query(..., description="User email address"),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_resolve_scope),
):
    """Resolve a user's DID and **every** credential they can present.

    One human legitimately holds several roles, so this returns all of them and
    lets the caller select the credential the operation requires. See
    ``UserResolveResponse`` for why the singular fields remain.
    """
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
    )

    # An expired credential is not presentable — the verifier rejects it — so
    # offering it as a candidate only produces a failure the caller cannot
    # explain. `status == "active"` alone does not imply unexpired.
    now = datetime.now(UTC)
    credentials = [
        _to_credential_response(c)
        for c in cred_result.scalars().all()
        if not _is_expired(c.expires_at, now)
    ]
    presentable = [c for c in credentials if c.vc_jws]
    newest = presentable[0] if presentable else None

    return UserResolveResponse(
        did=mapping.did,
        subject_id=mapping.subject_id,
        roles=[c.role for c in credentials if c.role],
        credentials=credentials,
        role=newest.role if newest else None,
        vc_jws=newest.vc_jws if newest else None,
    )
