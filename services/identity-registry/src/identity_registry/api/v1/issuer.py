"""The Issuer Service — DCP's Credential Issuance Protocol, anchor side.

Three endpoints, all from `credential.issuance.protocol.md`:

| Path | Is |
|---|---|
| `GET /issuer/metadata` | Issuer Metadata API — what this issuer can issue |
| `POST /issuer/credentials` | Credential Request API — a client asks to be issued to |
| `GET /issuer/requests/{issuerPid}` | Credential Request Status API |

**Why a separate base path from `/credentials`.** In DCP the Issuer Service and
the Credential Service are different services with different base URLs; ours are
in one image but they are not one role — `/credentials/{did}/…` is a *holder's*
surface and moves to the participant, `/issuer/…` is the issuer's and stays with
the trust anchor. Sharing a prefix would have made that split unstateable.

**No scope guard, deliberately, and it is not unauthenticated.** The caller is an
organisation that has been admitted but holds no credential yet — acquiring one
is what it is doing — so there is no token for `require_permission` to check. It
authenticates instead the way DCP says: a Self-Issued ID token proving control of
the DID it is registering, plus a `pre-authorized_code` naming the organisation.
Same reasoning as the invite-gated intake in `onboarding.py`, one step later.

**Every refusal answers alike.** This route is reachable by anyone, so a specific
error is an oracle: which codes exist, which organisations are verified, which
DIDs are already enrolled. The operator's log carries the real reason.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import CredentialRequest, Owner
from ...dependencies import get_db, get_did_resolver, get_settings_dep
from ...services import enrolment as enrol_service
from ...services.did_resolver import DidResolver
from ...services.token import SiTokenInvalid, verify_client_identity

log = logging.getLogger(__name__)

router = APIRouter(prefix="/issuer", tags=["issuer"])

DCP_CONTEXT = "https://w3id.org/dspace-dcp/v1.0/dcp.jsonld"

#: What this issuer issues, as CIP `CredentialObject`s. The `id` values are what
#: a `CredentialRequestMessage` names, and the spec requires every optional
#: property to be present on each entry in `credentialsSupported`.
#:
#: Both are *organisation* credentials. `DataSubjectCredential` is deliberately
#: absent: a natural person is not a holder and does not enrol (`D-49`), so
#: offering it here would advertise an exchange that has no second party.
CREDENTIALS_SUPPORTED: tuple[dict[str, Any], ...] = (
    {
        "id": "MembershipCredential",
        "type": "CredentialObject",
        "credentialType": "MembershipCredential",
        "offerReason": "enrolment",
        "bindingMethods": ["did:web"],
        "profile": "vc10-sl2021/jwt",
        "issuancePolicy": {},
    },
    {
        "id": "OrganizationCredential",
        "type": "CredentialObject",
        "credentialType": "OrganizationCredential",
        "offerReason": "enrolment",
        "bindingMethods": ["did:web"],
        "profile": "vc10-sl2021/jwt",
        "issuancePolicy": {},
    },
)

SUPPORTED_IDS = frozenset(obj["id"] for obj in CREDENTIALS_SUPPORTED)

_REFUSED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="Enrolment refused",
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing self-issued ID token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:].strip()


@router.get("/metadata")
async def issuer_metadata(settings: Settings = Depends(get_settings_dep)):
    """`IssuerMetadata` — the credential types this issuer supports.

    Public and unauthenticated by design: a client reads it *before* it has any
    identity here, to learn what to ask for. It discloses nothing about any
    organisation.
    """
    return {
        "@context": [DCP_CONTEXT],
        "type": "IssuerMetadata",
        "issuer": f"did:web:{settings.trust_anchor_domain}",
        "credentialsSupported": list(CREDENTIALS_SUPPORTED),
    }


@router.post("/credentials", status_code=status.HTTP_201_CREATED)
async def request_credentials(
    body: dict[str, Any],
    response: Response,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    resolver: DidResolver = Depends(get_did_resolver),
):
    """CIP Credential Request API — and, for a first request, enrolment.

    The exchange, in order, and every step is the specification's:

    1. verify the Self-Issued ID token: `iss == sub`, `aud` names this issuer,
       signature checked against the key in **the client's own DID document**,
       resolved over did:web (`base.protocol.md` §Validating Self-Issued ID
       Tokens);
    2. read `pre-authorized_code` — the code an operator issued when the
       organisation was admitted — and resolve it to a verified owner;
    3. register the client's DID, its **public** key and the service endpoints
       its document publishes;
    4. acknowledge with `201` and a `Location` pointing at the request status.

    Issuance itself is asynchronous and deliberately not done here: the spec
    splits acknowledgement from delivery, and so does the governance model —
    being admitted is not the same event as being issued to.

    **A retry is not a second enrolment.** The same DID re-presenting a valid
    code refreshes what it publishes; a *different* DID for an already-enrolled
    owner is refused, because re-pointing an organisation's identity is a
    decision for whoever issues the next token.
    """
    token = _bearer(authorization)

    if body.get("type") != "CredentialRequestMessage":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Expected a CredentialRequestMessage",
        )
    holder_pid = body.get("holderPid")
    if not isinstance(holder_pid, str) or not holder_pid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="holderPid is required"
        )

    requested = [
        entry.get("id")
        for entry in body.get("credentials") or []
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]
    unknown = sorted(set(requested) - SUPPORTED_IDS)
    if unknown:
        # Not an oracle: `credentialsSupported` is public, so naming what is not
        # in it discloses nothing the client could not already read.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported credential ids: {', '.join(unknown)}. "
                "See GET /issuer/metadata."
            ),
        )

    anchor_did = f"did:web:{settings.trust_anchor_domain}"
    try:
        client = await verify_client_identity(
            token, audience=anchor_did, resolver=resolver
        )
    except SiTokenInvalid as exc:
        log.warning("Rejected credential request: %s", exc)
        raise _REFUSED from exc

    try:
        enrolment_token = await enrol_service.resolve_enrolment_token(
            db, client.pre_authorized_code
        )
        owner = (
            await db.execute(
                select(Owner).where(Owner.id == enrolment_token.owner_alias)
            )
        ).scalar_one_or_none()
        if owner is None or owner.status != "verified":
            raise enrol_service.EnrolmentError(
                f"owner {enrolment_token.owner_alias!r} is missing or not verified"
            )

        outcome = await enrol_service.enrol(
            db,
            settings,
            owner=owner,
            token=enrolment_token,
            did=client.did,
            public_jwk=client.public_jwk,
            document=client.document,
        )
        request = await enrol_service.record_request(
            db,
            holder_pid=holder_pid,
            holder_did=client.did,
            owner_alias=owner.id,
            requested=requested,
        )
        await db.commit()
    except enrol_service.EnrolmentError as exc:
        await db.rollback()
        log.warning("Enrolment refused for %s: %s", client.did, exc.message)
        raise HTTPException(
            exc.status_code,
            detail=exc.public,
            headers={"WWW-Authenticate": "Bearer"}
            if exc.status_code == status.HTTP_401_UNAUTHORIZED
            else None,
        ) from exc

    # The allow path logs, not only the deny path. An enrolment that succeeded
    # silently is indistinguishable from one that never ran, which is the lesson
    # `NegotiationConsentValidator` and the STS both already carry.
    log.info(
        "Enrolled %s as %r (did=%s new, participant=%s new, dsp=%s, cs=%s) "
        "— requested %s",
        outcome.did,
        outcome.owner_alias,
        outcome.created_did,
        outcome.created_participant,
        outcome.dsp_address,
        outcome.credential_service_url,
        ", ".join(requested) or "nothing",
    )

    response.headers["Location"] = f"/issuer/requests/{request.issuer_pid}"
    return {
        "@context": [DCP_CONTEXT],
        "type": "CredentialStatus",
        "issuerPid": request.issuer_pid,
        "holderPid": request.holder_pid,
        "status": request.status,
    }


@router.get("/requests/{issuer_pid}")
async def request_status(
    issuer_pid: str,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    resolver: DidResolver = Depends(get_did_resolver),
):
    """CIP Credential Request Status API.

    *"The Issuer Service MUST implement access control such that only the client
    that made the request MAY access a particular request status."* So the SI
    token is verified the same way, and its `iss` must be the DID that made the
    request.

    An unknown request and someone else's request answer identically: a `404`
    that distinguished them would let a holder enumerate other holders' requests.
    """
    token = _bearer(authorization)
    anchor_did = f"did:web:{settings.trust_anchor_domain}"
    try:
        client = await verify_client_identity(
            token, audience=anchor_did, resolver=resolver
        )
    except SiTokenInvalid as exc:
        raise _REFUSED from exc

    request = (
        await db.execute(
            select(CredentialRequest).where(
                CredentialRequest.issuer_pid == issuer_pid,
                CredentialRequest.holder_did == client.did,
            )
        )
    ).scalar_one_or_none()
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such request")

    return {
        "@context": [DCP_CONTEXT],
        "type": "CredentialStatus",
        "issuerPid": request.issuer_pid,
        "holderPid": request.holder_pid,
        "status": request.status,
    }
