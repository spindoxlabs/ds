from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import Did, StatusList
from ...dependencies import get_db, get_settings_dep
from ...services import trust_list
from ...services.crypto import decrypt_private_jwk
from ...services.did import build_did_document
from ...services.org_onboarding import OrgOnboardingError, get_trust_anchor_key
from ...services.status_list import build_status_list_credential, encode_bitstring
from ...services.vc import sign_credential

# Two routers, because the two things this file serves belong to different
# roles once the registry is split (`DID-04`). **DID resolution is the holder's**
# — a document is served by whichever instance holds that DID's key, which is
# the corrected reading of rulebook `P-6`. **The StatusList is the issuer's**:
# one list, published by the trust anchor, and a participant serving its own
# would be a participant asserting its own credentials are unrevoked.
did_router = APIRouter(tags=["public"])
status_router = APIRouter(tags=["public"])
#: The trust list. Anchor-only and public — see the route.
trust_router = APIRouter(tags=["public"])


async def _did_document(did: str, db: AsyncSession) -> dict:
    """Serve the document for a DID this instance publishes.

    `P-6` — *a DID document is served only for a DID the registry holds a key
    for* — is enforced here, and it now has one deliberate exception: a **user**
    DID has no key at all (`D-49`). A subject presents nothing and signs nothing,
    so a key would be read by nobody; but the DID must still resolve, because it
    is the identifier consent records and provenance events point at. That is
    `personal-data.md` `D-22`.

    A **participant** DID with no key is still a 404, and that is the rule doing
    its job: it means this registry recorded that a party exists without being
    shown a key, so it is not the one that publishes their document.
    """
    result = await db.execute(select(Did).where(Did.did == did, Did.active.is_(True)))
    did_record = result.scalar_one_or_none()
    if not did_record:
        raise HTTPException(status_code=404, detail="DID not found")
    if not did_record.key and did_record.did_type != "user":
        raise HTTPException(status_code=404, detail="DID has no key")

    return build_did_document(
        did=did_record.did,
        public_jwk=did_record.key.public_jwk if did_record.key else None,
        did_type=did_record.did_type,
        service_endpoints=did_record.service_endpoints,
    )


@did_router.get("/dids/{did:path}/did.json")
async def resolve_did(did: str, db: AsyncSession = Depends(get_db)):
    return JSONResponse(
        content=await _did_document(did, db),
        media_type="application/did+ld+json",
    )


@did_router.get("/.well-known/did.json")
async def resolve_host_did(request: Request, db: AsyncSession = Depends(get_db)):
    """Serve the document for the DID this host *is* — the did:web mapping itself.

    ``did:web:provider.example.org`` resolves to
    ``https://provider.example.org/.well-known/did.json``, so a registry reached
    on that host can answer for that DID with no help from anything in front of
    it. Caddy and the Ingress each carry a rewrite to `/dids/{did}/did.json`
    instead, which means DID resolution — the root of every trust decision — has
    been a property of the proxy configuration rather than of the service, and a
    deployment that fronts this differently silently has no resolvable DIDs.

    The port is percent-encoded exactly as the did:web method requires, which is
    what lets a test — or a deployment on a non-standard port — resolve at all.
    """
    host = (request.headers.get("host") or "").split(",")[0].strip()
    if not host:
        raise HTTPException(status_code=404, detail="DID not found")
    did = "did:web:" + host.replace(":", "%3A")
    return JSONResponse(
        content=await _did_document(did, db),
        media_type="application/did+ld+json",
    )


@did_router.get("/{did_path:path}/did.json")
async def resolve_path_did(
    did_path: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """The did:web *path* form: ``did:web:host:a:b`` → ``/a/b/did.json``.

    The sibling of the route above, and what makes a person's DID
    (``did:web:<participant>:users:<id>``) resolvable by **this** service — the
    organisation that holds their credentials — rather than by a proxy rewrite
    against a flat `users.<domain>` host owned by the trust anchor (`DID-11`
    step 2).

    **Registered last on purpose.** It is a catch-all, and a catch-all declared
    before its siblings is how `/dids/{did}/did.json` would start 404ing as an
    unknown DID — the same shape as `POST /catalog/search` in the connector.
    """
    host = (request.headers.get("host") or "").split(",")[0].strip()
    if not host or not did_path:
        raise HTTPException(status_code=404, detail="DID not found")
    segments = "/".join(part for part in did_path.split("/") if part)
    did = "did:web:" + host.replace(":", "%3A") + ":" + segments.replace("/", ":")
    return JSONResponse(
        content=await _did_document(did, db),
        media_type="application/did+ld+json",
    )


@status_router.get("/status/{list_id}")
async def get_status_list(
    list_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """The revocation list, **signed**, as a VC-JWT.

    A verifier fetches this to decide whether a credential it was shown is still
    valid, so an unsigned list is a list anyone on the path can rewrite: clear a
    bit and a revoked credential is accepted again. It was served as plain
    JSON-LD with no proof of any kind.

    EDC — and any implementation following it — sends `Accept: */*` and treats
    the body as a JWT (`BaseRevocationListService.parseStatusListCredentialResponse`
    takes the JSON branch **only** when the accept header is exactly
    `application/json`). So the JWT is the default and JSON is opt-in, which is
    also the safer way round: a caller that asks for no particular format gets
    the verifiable one.
    """
    result = await db.execute(select(StatusList).where(StatusList.id == list_id))
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="Status list not found")

    trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"
    credential = build_status_list_credential(
        list_id=list_id,
        issuer_did=trust_anchor_did,
        encoded_list=encode_bitstring(sl.bitstring),
        purpose=sl.purpose,
    )

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "*/*" not in accept:
        return JSONResponse(content=credential, media_type="application/ld+json")

    try:
        key = await get_trust_anchor_key(db, settings)
    except OrgOnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    signed = sign_credential(
        credential,
        decrypt_private_jwk(key.private_jwk, settings.encryption_key),
        key.kid,
    )
    return PlainTextResponse(
        content=signed["proof"]["jws"],
        media_type="application/vc+jwt",
    )


@trust_router.get("/trust")
async def get_trust_list(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    """The dataspace's list of accredited entities (`DSSC-TRF-05`, `-07`, `-17`).

    **Public and unauthenticated**, for the same reason the revocation list is
    (`P-13`): a counterparty deciding whether to accept a credential must be able
    to read it *before* it has any relationship with this dataspace. It is also
    the first document another dataspace initiative reads about us — a federation
    partner asks "whose attestations does this dataspace stand behind" before it
    asks anything else.

    It discloses nothing sensitive: every entry is a DID that already resolves
    publicly, and the fact that this dataspace accredits its own trust anchor is
    not a secret — it is the point.

    **Revoked entries are included**, which the specification requires in as many
    words. A list that forgets what it used to trust cannot answer whether a
    credential already in circulation was legitimate when it was issued.
    """
    return JSONResponse(
        content=trust_list.render(await trust_list.entries(db), settings),
        media_type="application/json",
    )
