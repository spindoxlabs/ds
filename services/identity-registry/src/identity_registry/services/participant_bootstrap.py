"""Participant side of enrolment — generate a key, publish a DID, present proof.

The counterpart of `enrolment.py`. That module is what the **anchor** does when
somebody enrols; this is what an **organisation's own instance** does to enrol.
They never share a database, and after `DID-05` they never share a process.

Two steps, and the order is the point:

1. **`ensure_identity`** — generate an EC P-256 keypair, encrypt the private half
   with *this instance's own* `IDENTITY_REGISTRY_ENCRYPTION_KEY`, and write the
   `Did` + `Key` rows with the service entries this participant publishes. After
   this the instance serves its own `did.json`, and **nothing outside it has ever
   seen the private key**. That sentence is the whole of `D-47`.

2. **`enrol`** — mint a Self-Issued ID token with that key (`iss = sub = own
   DID`, `aud = the anchor`, `pre-authorized_code = the code an operator issued`)
   and `POST` a `CredentialRequestMessage` to the anchor's Issuer Service.

**Step 1 is useful without step 2 and the reverse is impossible**, which is why
they are separate functions. An instance can hold its identity and serve DCP
before the anchor knows about it; it cannot prove anything to the anchor without
first holding a key.

## The ordering trap this will hit in dev

The anchor verifies the request by resolving the client's DID **over did:web** —
that is deliberate and has no local shortcut (see `verify_client_identity`). So
the participant's `did.json` has to be reachable *from the anchor* before it
enrols: the instance must be serving, and whatever routes `did:web` to it (Caddy,
an Ingress) must already point there. Enrolling from a container that is up but
not yet routed fails with a resolution error, and the error will name the URL
that could not be fetched.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Did, Key, Participant
from .crypto import encrypt_private_jwk, generate_key_pair, hash_sts_secret
from .enrolment import CREDENTIAL_SERVICE_TYPE, DSP_ENDPOINT_TYPE
from .token import create_self_signed_token

log = logging.getLogger(__name__)

DCP_CONTEXT = "https://w3id.org/dspace-dcp/v1.0/dcp.jsonld"


class ParticipantBootstrapError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class LocalIdentity:
    did: str
    kid: str
    created: bool
    service_endpoints: list[dict[str, str]]
    #: True when this run created the local `Participant` row — the record that
    #: makes this instance its own STS.
    created_participant: bool = False


def _endpoints(settings: Settings, did: str) -> list[dict[str, str]]:
    entries = [
        {
            "type": CREDENTIAL_SERVICE_TYPE,
            "serviceEndpoint": settings.credential_service_url(did),
        }
    ]
    if settings.participant_dsp_address:
        entries.insert(
            0,
            {
                "type": DSP_ENDPOINT_TYPE,
                "serviceEndpoint": settings.participant_dsp_address,
            },
        )
    return entries


async def ensure_identity(
    db: AsyncSession, settings: Settings, *, did: str | None = None
) -> LocalIdentity:
    """Generate and hold this instance's own DID key. Idempotent.

    Re-running refreshes the published service endpoints and leaves the key
    alone: a bootstrap that ran a second time and rotated the key would
    invalidate every credential bound to the old one, silently, on a pod restart.
    Rotation is `ir-cli key rotate` and is a decision, not a side effect.
    """
    did = did or settings.participant_did
    if not did:
        raise ParticipantBootstrapError(
            "No DID configured. Set IDENTITY_REGISTRY_PARTICIPANT_DID to the DID "
            "this instance holds the key for."
        )

    endpoints = _endpoints(settings, did)

    existing_key = (
        await db.execute(select(Key).where(Key.owner_did == did, Key.active.is_(True)))
    ).scalar_one_or_none()
    did_row = (await db.execute(select(Did).where(Did.did == did))).scalar_one_or_none()

    if existing_key is not None and existing_key.private_jwk is None:
        # A public-only row here means this instance recorded somebody *else's*
        # key under its own DID — a misconfiguration where two instances were
        # pointed at one database, which is exactly what the split exists to
        # prevent. Refuse rather than generating a second key beside it.
        raise ParticipantBootstrapError(
            f"{did} already has a public-only key in this database — this "
            "instance does not hold its private half. Two instances are sharing "
            "a database, or PARTICIPANT_DID names another participant."
        )

    if existing_key is None:
        kp = generate_key_pair(did)
        key = Key(
            owner_did=did,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
            public_jwk=kp.public_jwk,
        )
        db.add(key)
        await db.flush()
        created = True
    else:
        key = existing_key
        created = False

    if did_row is None:
        db.add(
            Did(
                did=did,
                did_type="participant",
                key_id=key.id,
                service_endpoints=endpoints,
            )
        )
    else:
        did_row.key_id = key.id
        did_row.service_endpoints = endpoints
        did_row.active = True
        did_row.deactivated_at = None
    await db.flush()

    # **This instance is its own STS**, and `POST /sts/{did}/token` reads a local
    # `Participant` row with a stored secret to decide that (`sts.py`). Without
    # one, a participant instance 401s its own connector: the DID resolves, the
    # credential service answers, and the very first token request fails — the
    # kind of break that looks like a credential problem three services away.
    #
    # The secret is **this participant's own** (`D-51`). The anchor's copy of the
    # `Participant` row deliberately carries none, because the anchor is not this
    # participant's STS and must not be able to act as it.
    participant = (
        await db.execute(select(Participant).where(Participant.did == did))
    ).scalar_one_or_none()
    created_participant = participant is None
    if participant is None:
        participant = Participant(
            did=did,
            dsp_address=settings.participant_dsp_address,
            roles=[],
            allowed_scopes=[],
            sts_client_secret=hash_sts_secret(settings.participant_sts_secret),
        )
        db.add(participant)
    else:
        participant.sts_client_secret = hash_sts_secret(settings.participant_sts_secret)
        if settings.participant_dsp_address:
            participant.dsp_address = settings.participant_dsp_address
        participant.active = True
        participant.deactivated_at = None
    await db.flush()

    log.info(
        "Local identity %s: %s (kid=%s), publishing %s; STS %s",
        "generated" if created else "already held",
        did,
        key.kid,
        ", ".join(e["type"] for e in endpoints),
        "registered" if created_participant else "secret refreshed",
    )
    return LocalIdentity(
        did=did,
        kid=key.kid,
        created=created,
        service_endpoints=endpoints,
        created_participant=created_participant,
    )


async def _si_token(
    db: AsyncSession,
    settings: Settings,
    did: str,
    *,
    audience: str,
    code: str | None,
    ttl: int = 300,
) -> str:
    """This instance's own SI token, carrying the enrolment code.

    The claim name is DCP's, not ours: `credential.issuance.protocol.md`
    §Credential Request API names `pre-authorized_code` as how a client presents
    a pre-authorization code to an issuer.
    """
    try:
        return await create_self_signed_token(
            db,
            settings,
            did,
            audience=audience,
            extra_claims={"pre-authorized_code": code} if code else None,
            token_ttl=ttl,
        )
    except LookupError as exc:
        raise ParticipantBootstrapError(
            f"No private key for {did} — run the identity step before enrolling."
        ) from exc


@dataclass(slots=True)
class EnrolmentResult:
    issuer_pid: str
    holder_pid: str
    status: str
    location: str | None


async def enrol(
    db: AsyncSession,
    settings: Settings,
    *,
    code: str,
    did: str | None = None,
    credentials: tuple[str, ...] = ("MembershipCredential", "OrganizationCredential"),
    timeout: float = 10.0,
) -> EnrolmentResult:
    """Present this instance's key to the anchor and ask to be issued to.

    The request body carries **no endpoints and no key** — both are read by the
    anchor from the DID document this instance publishes, which is the only copy
    that can be checked against a signature.
    """
    did = did or settings.participant_did
    if not did:
        raise ParticipantBootstrapError(
            "No DID configured. Set IDENTITY_REGISTRY_PARTICIPANT_DID."
        )

    holder_pid = str(uuid.uuid4())
    token = await _si_token(
        db, settings, did, audience=settings.trust_anchor_did, code=code
    )
    url = f"{settings.issuer_base_url}/issuer/credentials"
    body = {
        "@context": [DCP_CONTEXT],
        "type": "CredentialRequestMessage",
        "holderPid": holder_pid,
        "credentials": [{"id": name} for name in credentials],
    }

    async with httpx.AsyncClient(timeout=timeout) as http:
        try:
            response = await http.post(
                url, json=body, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as exc:
            raise ParticipantBootstrapError(
                f"Could not reach the issuer at {url}: {exc}"
            ) from exc

    if response.status_code >= 400:
        # The anchor deliberately does not say which half failed. Say what *this*
        # side can check, because those are the two things an operator can fix.
        raise ParticipantBootstrapError(
            f"Enrolment refused ({response.status_code}) by {url}: "
            f"{response.text.strip()[:200]}. Check that the enrolment code is "
            f"current, and that {did} resolves from the anchor — the anchor "
            "fetches the DID document itself and verifies the signature against "
            "the key published there."
        )

    payload = response.json()
    log.info(
        "Enrolled %s with %s — issuerPid=%s status=%s",
        did,
        settings.issuer_base_url,
        payload.get("issuerPid"),
        payload.get("status"),
    )
    return EnrolmentResult(
        issuer_pid=str(payload.get("issuerPid") or ""),
        holder_pid=str(payload.get("holderPid") or holder_pid),
        status=str(payload.get("status") or ""),
        location=response.headers.get("Location"),
    )
