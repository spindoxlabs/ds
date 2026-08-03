"""Enrolment — a verified organisation registers the key it generated itself.

The seam between the **governance plane** (a candidate applies, is verified,
accepts the terms, is admitted — all human judgement, all recorded here) and the
**operation plane** (DSP, DCP, transfers). Before this existed the two were
joined by a *mint*: the anchor generated the organisation's keypair, kept the
private half, and handed back an STS secret. That is one party doing what needs
two, and it is the whole of the `§3.1` custody deviation.

Enrolment replaces it with a handshake:

    anchor                                    organisation's own instance
    ──────                                    ───────────────────────────
    admitted → enrolment token (out of band) ──▶
                                               generate keypair, publish did.json
    ◀── POST /issuer/credentials
        Authorization: Bearer <SI token>
          iss = sub = its DID
          aud = the anchor's DID
          pre-authorized_code = the token
    verify signature ← the DID document at
      the client's own host
    register DID + **public** key + endpoints

**Two independent factors, and neither is sufficient.** The code says *which
organisation*; the signature says *which key*. A leaked code without the key
binds nothing; a key without a code is a stranger. That is what makes this an
enrolment rather than a hand-over, and it is where `DSSC-IAM-13` (proof of
control) is actually satisfied — previously nowhere, because the anchor
generated the key and so had nothing to verify.

## This is DCP's Credential Issuance Protocol, not a local invention

Every element is the spec's. `credential.issuance.protocol.md` §Issuance Flow
steps 1–6 are exactly the exchange above, `base.protocol.md` §Validating
Self-Issued ID Tokens is the check, and the authorization carrier is named by the
spec in as many words: *"if the issuer supports a pre-authorization code flow,
the client MUST use the `pre-authorized_code` claim in the Self-Issued ID
Token"*. Building it in that shape now is why `DID-14` is conformance work on
message names rather than a second implementation.

## Where the endpoints come from

**The client's DID document, not the request body.** A participant declares its
own DSP address and credential service as `service` entries in the document it
publishes, and the anchor reads them from the document it just resolved to check
the signature. The alternative — fields in the request — would let a client
claim endpoints its DID document does not carry, and would mean two sources for
one fact.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import CredentialRequest, Did, EnrolmentToken, Key, Owner, Participant

#: The `service` entry types a participant publishes and this registry records.
DSP_ENDPOINT_TYPE = "DSPEndpoint"
CREDENTIAL_SERVICE_TYPE = "CredentialService"


class EnrolmentError(Exception):
    """Enrolment refused.

    ``public`` is what the client is told and is deliberately vague; ``message``
    is what the operator sees in the log. The endpoint is reachable before any
    credential exists, so a precise refusal is an oracle: *"that code is spent"*
    versus *"that code is unknown"* tells an attacker which codes exist, and
    *"that owner has no accepted agreement"* discloses the state of an
    organisation's application to anyone holding a key.
    """

    def __init__(
        self, message: str, *, status_code: int = 401, public: str | None = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.public = public or "Enrolment refused"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedEnrolmentToken:
    """Returned once, on issue. The registry keeps only the hash."""

    id: str
    code: str
    owner_alias: str
    expires_at: datetime | None


async def create_enrolment_token(
    db: AsyncSession,
    owner_alias: str,
    *,
    ttl_days: int | None = 14,
    label: str | None = None,
    created_by: str | None = None,
    roles: list[str] | None = None,
    allowed_scopes: list[str] | None = None,
) -> IssuedEnrolmentToken:
    """Issue the code an admitted organisation enrols with.

    Refuses for an owner that is not **verified** — an enrolment token for an
    unverified organisation is an admission decision taken by whoever generated
    the token, which is the governance plane being bypassed by the tool meant to
    serve it. Onboarding's own `POST /admin/owners` refuses to create
    organisations for the same reason.

    The agreement is *not* checked here. Acceptance can legitimately come after
    admission, and issuance — not enrolment — is where it gates.
    """
    owner = (
        await db.execute(select(Owner).where(Owner.id == owner_alias))
    ).scalar_one_or_none()
    if owner is None:
        raise EnrolmentError(
            f"Owner {owner_alias!r} does not exist",
            status_code=404,
            public=f"Owner {owner_alias!r} does not exist",
        )
    if owner.status != "verified":
        raise EnrolmentError(
            f"Owner {owner_alias!r} is {owner.status!r}; only a verified "
            "organisation may be issued an enrolment token",
            status_code=409,
            public=f"Owner {owner_alias!r} is not verified",
        )

    code = secrets.token_urlsafe(32)
    token = EnrolmentToken(
        code_hash=hash_code(code),
        owner_alias=owner_alias,
        label=label,
        created_by=created_by,
        roles=list(roles) if roles else None,
        allowed_scopes=list(allowed_scopes) if allowed_scopes else None,
        expires_at=(
            datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None
        ),
    )
    db.add(token)
    await db.flush()
    return IssuedEnrolmentToken(
        id=token.id,
        code=code,
        owner_alias=owner_alias,
        expires_at=token.expires_at,
    )


def _expired(token: EnrolmentToken, now: datetime) -> bool:
    if token.expires_at is None:
        return False
    expires = token.expires_at
    # SQLite drops tzinfo; stored timestamps are UTC by convention.
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= now


async def resolve_enrolment_token(
    db: AsyncSession, code: str | None
) -> EnrolmentToken:
    """The token for *code*, if it is usable. One refusal for every failure."""
    refused = EnrolmentError("invalid, spent or expired enrolment code")
    if not code:
        raise EnrolmentError("no pre-authorized_code presented")

    token = (
        await db.execute(
            select(EnrolmentToken).where(EnrolmentToken.code_hash == hash_code(code))
        )
    ).scalar_one_or_none()
    if token is None or token.redeemed_at is not None:
        raise refused
    if _expired(token, datetime.now(UTC)):
        raise refused
    return token


def service_endpoints(document: dict[str, Any]) -> list[dict[str, str]]:
    """The `service` entries of a DID document, in this registry's own shape.

    Tolerant of what it reads and strict about what it stores: a `service` block
    is somebody else's JSON-LD, so entries missing a type or an endpoint are
    dropped rather than stored half-formed, and `serviceEndpoint` may be a string
    or an object with an `origin`/`uri` (both appear in the wild).
    """
    entries: list[dict[str, str]] = []
    for entry in document.get("service") or []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        endpoint = entry.get("serviceEndpoint")
        if isinstance(endpoint, dict):
            endpoint = endpoint.get("origin") or endpoint.get("uri")
        if isinstance(kind, str) and isinstance(endpoint, str) and kind and endpoint:
            entries.append({"type": kind, "serviceEndpoint": endpoint})
    return entries


def endpoint_of(entries: list[dict[str, str]], kind: str) -> str | None:
    for entry in entries:
        if entry["type"] == kind:
            return entry["serviceEndpoint"]
    return None


@dataclass(slots=True)
class EnrolmentOutcome:
    """What enrolling changed. Reported, so a bootstrap log says what happened."""

    owner_alias: str
    did: str
    created_did: bool
    created_participant: bool
    dsp_address: str | None
    credential_service_url: str | None


async def enrol(
    db: AsyncSession,
    settings: Settings,
    *,
    owner: Owner,
    token: EnrolmentToken,
    did: str,
    public_jwk: dict[str, Any],
    document: dict[str, Any],
    roles: list[str] | None = None,
    allowed_scopes: list[str] | None = None,
) -> EnrolmentOutcome:
    """Bind *did* and its public key to *owner*, and register the participant.

    Idempotent for the same DID — an enrolment retried after a network failure
    must not need an operator — but **never re-points an owner at a different
    DID**. Rebinding an organisation's identity to a new key is a re-enrolment
    decision the governance plane makes by issuing another token, not something
    a keyholder does by asking twice.
    """
    # What the token admits, not what the request asks for.
    roles = list(token.roles or roles or [])
    allowed_scopes = list(token.allowed_scopes or allowed_scopes or [])

    if owner.did and owner.did != did:
        raise EnrolmentError(
            f"Owner {owner.id!r} is already enrolled as {owner.did}; enrolling "
            f"{did} would re-point the organisation's identity",
            status_code=409,
            public="This organisation is already enrolled",
        )

    kid = public_jwk.get("kid")
    if not isinstance(kid, str) or not kid:
        raise EnrolmentError(
            "the resolved DID document's verification method has no kid",
            status_code=422,
            public="The DID document is not usable for enrolment",
        )
    if "d" in public_jwk:
        # A client that sent us its private key has misconfigured something
        # badly enough that continuing would store it. Refuse loudly: this is the
        # one error worth being specific about, because the fix is on their side
        # and the alternative is a private key at rest in the anchor — the exact
        # state this whole change exists to end.
        raise EnrolmentError(
            "the presented verification key contains a private component ('d')",
            status_code=422,
            public="The DID document publishes a private key — refusing",
        )

    endpoints = service_endpoints(document)
    dsp_address = endpoint_of(endpoints, DSP_ENDPOINT_TYPE)
    credential_service_url = endpoint_of(endpoints, CREDENTIAL_SERVICE_TYPE)

    did_row = (
        await db.execute(select(Did).where(Did.did == did))
    ).scalar_one_or_none()
    created_did = did_row is None

    if did_row is None:
        key = Key(owner_did=did, kid=kid, private_jwk=None, public_jwk=public_jwk)
        db.add(key)
        await db.flush()
        did_row = Did(
            did=did,
            did_type="participant",
            display_name=owner.name,
            key_id=key.id,
            service_endpoints=endpoints or None,
        )
        db.add(did_row)
        await db.flush()
    else:
        # Re-enrolment of the same DID: refresh what the participant publishes,
        # and adopt a rotated key. Never overwrite a private key we hold — that
        # is a locally-held DID (the anchor's own), and enrolment is not how it
        # changes.
        existing = (
            await db.execute(
                select(Key).where(Key.owner_did == did, Key.active.is_(True))
            )
        ).scalar_one_or_none()
        if existing is not None and existing.private_jwk is not None:
            raise EnrolmentError(
                f"{did} is held locally by this instance; enrolment cannot "
                "replace a key this registry generated",
                status_code=409,
                public="This DID cannot be enrolled here",
            )
        if existing is None:
            key = Key(owner_did=did, kid=kid, private_jwk=None, public_jwk=public_jwk)
            db.add(key)
            await db.flush()
            did_row.key_id = key.id
        elif existing.kid != kid:
            existing.active = False
            existing.rotated_at = datetime.now(UTC)
            key = Key(owner_did=did, kid=kid, private_jwk=None, public_jwk=public_jwk)
            db.add(key)
            await db.flush()
            did_row.key_id = key.id
        else:
            existing.public_jwk = public_jwk
        if endpoints:
            did_row.service_endpoints = endpoints
        did_row.active = True
        did_row.deactivated_at = None
        await db.flush()

    owner.did = did
    owner.updated_at = datetime.now(UTC)

    participant = (
        await db.execute(select(Participant).where(Participant.did == did))
    ).scalar_one_or_none()
    created_participant = participant is None
    if participant is None:
        participant = Participant(
            did=did,
            dsp_address=dsp_address,
            roles=list(roles or []),
            allowed_scopes=list(allowed_scopes or []),
            # **No STS secret.** The participant's STS is its own instance, and
            # it mints whatever secret that needs. A value here would be this
            # registry deciding how somebody else authenticates to themselves.
            sts_client_secret=None,
        )
        db.add(participant)
    else:
        if dsp_address:
            participant.dsp_address = dsp_address
        if roles:
            participant.roles = list(roles)
        if allowed_scopes:
            participant.allowed_scopes = list(allowed_scopes)
        participant.active = True
        participant.deactivated_at = None

    token.redeemed_at = datetime.now(UTC)
    token.redeemed_did = did
    await db.flush()

    return EnrolmentOutcome(
        owner_alias=owner.id,
        did=did,
        created_did=created_did,
        created_participant=created_participant,
        dsp_address=dsp_address,
        credential_service_url=credential_service_url,
    )


async def record_request(
    db: AsyncSession,
    *,
    holder_pid: str,
    holder_did: str,
    owner_alias: str | None,
    requested: list[str],
    status: str = "RECEIVED",
    detail: str | None = None,
) -> CredentialRequest:
    request = CredentialRequest(
        holder_pid=holder_pid,
        holder_did=holder_did,
        owner_alias=owner_alias,
        requested=requested,
        status=status,
        detail=detail,
    )
    db.add(request)
    await db.flush()
    return request
