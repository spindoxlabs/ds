from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Credential, KeycloakMapping
from ...dependencies import get_db, require_read_scope, require_resolve_scope
from ...schemas.responses import (
    SubjectIdentityResponse,
    UserCredentialResponse,
    UserResolveResponse,
)

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


class SubjectIdentitiesRequest(BaseModel):
    """DIDs to translate into the identifiers other systems key on."""

    dids: list[str]


@router.post("/identities", response_model=list[SubjectIdentityResponse])
async def resolve_subject_identities(
    body: SubjectIdentitiesRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_read_scope),
):
    """Translate subject DIDs into the username a non-dataspace system keys on.

    A dataspace decision names people by DID. The systems that hold their data
    do not: the REC registry resolves a member by Keycloak's
    ``preferred_username``. Something has to bridge the two, and it has to be
    the registry that already stores the link — deriving it anywhere else means
    guessing, and a wrong guess reads another person's data.

    **Batched on purpose.** The caller is resolving the whole consented-subject
    set for one query; one request per subject would put a fan-out on the hot
    path of every data-plane read.

    A DID with no mapping is **omitted** rather than returned empty, and no
    error is raised: the caller must not be able to tell "unknown subject" from
    "subject with no username", or this becomes a directory of who exists.
    """
    if not body.dids:
        return []
    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.did.in_(body.dids))
    )
    identities = []
    for mapping in result.scalars().all():
        # `email` is the documented fallback: this realm sets username = email,
        # and rows predating the column carry only the email. Nothing further is
        # inferred.
        username = mapping.username or mapping.email
        if not username:
            continue
        identities.append(
            SubjectIdentityResponse(did=mapping.did, username=username)
        )
    return identities
