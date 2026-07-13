from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Did, StatusList
from ...dependencies import get_db
from ...services.did import build_did_document
from ...services.status_list import build_status_list_credential, encode_bitstring

router = APIRouter(tags=["public"])


@router.get("/dids/{did:path}/did.json")
async def resolve_did(did: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Did).where(Did.did == did, Did.active.is_(True)))
    did_record = result.scalar_one_or_none()
    if not did_record:
        raise HTTPException(status_code=404, detail="DID not found")
    if not did_record.key:
        raise HTTPException(status_code=404, detail="DID has no key")

    doc = build_did_document(
        did=did_record.did,
        public_jwk=did_record.key.public_jwk,
        did_type=did_record.did_type,
        service_endpoints=did_record.service_endpoints,
    )
    return JSONResponse(
        content=doc,
        media_type="application/did+ld+json",
    )


@router.get("/status/{list_id}")
async def get_status_list(list_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(StatusList).where(StatusList.id == list_id)
    )
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="Status list not found")

    from ...config import get_settings

    settings = get_settings()
    trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"

    credential = build_status_list_credential(
        list_id=list_id,
        issuer_did=trust_anchor_did,
        encoded_list=encode_bitstring(sl.bitstring),
        purpose=sl.purpose,
    )
    return JSONResponse(
        content=credential,
        media_type="application/ld+json",
    )
