"""Issuance and delivery — the second leg of DCP's Credential Issuance Protocol.

`enrolment.py` is CIP steps 1–6: a client proves control of its DID and the
issuer acknowledges. This is steps 7–8: the issuer signs the credentials, reads
the client's `CredentialService` endpoint **from the DID document it already
resolved**, and writes them there over the Storage API.

**Why the credentials cannot simply stay here.** A presentation query is answered
by the participant's own credential service, from the participant's own database
(`presentation.py` selects `Credential` rows where `subject_did` is the holder).
An enrolled participant with no credentials in its own store answers every query
with an empty presentation — a correct-looking response that grants nothing, and
one of the quieter ways this platform could look decentralized and not work.

**The anchor keeps its own record of every credential it issued**, and that is
not a duplicate: it is the issuance register that `GET /credentials/check` reads
and that revocation acts on. The issuer knows *what it attested*; the holder
holds *what it can present*. Those are different facts about the same credential.

## Failure is partial by nature, and says so

Signing happens here; delivery happens over the network to somebody else's
service. A push that fails leaves a credential the anchor has issued and the
participant does not hold — so the request is recorded `REJECTED` with the reason,
the issued rows stay (they are what a retry re-delivers rather than re-mints), and
nothing pretends the exchange completed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Credential, Owner, Participant
from .crypto import decrypt_private_jwk, generate_credential_id
from .enrolment import CREDENTIAL_SERVICE_TYPE, endpoint_of, service_endpoints
from .org_onboarding import OrgOnboardingError, get_trust_anchor_key
from .status_list import allocate_status_list_index
from .token import create_self_signed_token
from .vc import build_membership_credential, sign_credential

log = logging.getLogger(__name__)

DCP_CONTEXT = "https://w3id.org/dspace-dcp/v1.0/dcp.jsonld"

MEMBERSHIP = "MembershipCredential"
ORGANIZATION = "OrganizationCredential"


class IssuanceError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class IssuanceOutcome:
    """What was signed, what was delivered, and what was not."""

    issued: list[str] = field(default_factory=list)
    withheld: dict[str, str] = field(default_factory=dict)
    delivered_to: str | None = None
    error: str | None = None

    @property
    def status(self) -> str:
        """CIP's vocabulary: `RECEIVED` | `REJECTED` | `ISSUED`."""
        if self.error or not self.issued:
            return "REJECTED"
        return "ISSUED"

    @property
    def detail(self) -> str | None:
        parts = [f"{name}: {why}" for name, why in sorted(self.withheld.items())]
        if self.error:
            parts.append(self.error)
        return "; ".join(parts) or None


async def issue_for_participant(
    db: AsyncSession,
    settings: Settings,
    *,
    owner: Owner,
    did: str,
    requested: list[str],
    document: dict,
) -> IssuanceOutcome:
    """Sign what *did* asked for and can have, then deliver it to its store.

    `MembershipCredential` needs a verified owner, which enrolment already
    required. `OrganizationCredential` additionally needs an **accepted
    agreement** — the §5.6 gate — so a participant that enrolled before signing
    the terms gets its membership and is told, in `detail`, what is waiting on
    what. Withholding it silently would leave an organisation looking issued-to
    while a credential the rulebook requires is missing.
    """
    outcome = IssuanceOutcome()

    participant = (
        await db.execute(select(Participant).where(Participant.did == did))
    ).scalar_one_or_none()
    if participant is None:
        raise IssuanceError(f"{did} is not a registered participant")

    try:
        anchor_key = await get_trust_anchor_key(db, settings)
    except OrgOnboardingError as exc:
        # An issuer with no issuing key is a deployment that was never
        # bootstrapped. Name it as such rather than letting a service-layer
        # exception surface as an opaque 500 three layers up.
        raise IssuanceError(
            f"this instance cannot issue: {exc.message}"
        ) from exc
    anchor_did = settings.trust_anchor_did
    anchor_jwk = decrypt_private_jwk(anchor_key.private_jwk, settings.encryption_key)
    ttl = min(settings.default_credential_ttl_days, settings.max_credential_ttl_days)

    signed: list[tuple[str, dict]] = []

    for name in requested or [MEMBERSHIP]:
        if name == ORGANIZATION and not owner.agreement_id:
            outcome.withheld[name] = (
                "no accepted agreement — issue it once the organisation has "
                "accepted a current agreement version"
            )
            continue
        if name not in (MEMBERSHIP, ORGANIZATION):
            outcome.withheld[name] = "not a credential this issuer offers"
            continue

        existing = await _active_credential(db, did, name)
        if existing is not None:
            # A re-enrolment must not mint a second credential and burn another
            # StatusList index. Re-delivering the one that exists is what a retry
            # after a failed push needs, and it is what this does.
            signed.append((name, existing.credential_json))
            outcome.issued.append(name)
            continue

        if name == MEMBERSHIP:
            for vc, index in await _membership_credentials(
                db, settings, participant, anchor_did, ttl
            ):
                signed_vc = sign_credential(vc, anchor_jwk, anchor_key.kid)
                db.add(
                    Credential(
                        id=signed_vc["id"],
                        credential_type=name,
                        issuer_did=anchor_did,
                        subject_did=did,
                        credential_json=signed_vc,
                        status_list_index=index,
                        expires_at=datetime.now(UTC) + timedelta(days=ttl),
                    )
                )
                await db.flush()
                signed.append((name, signed_vc))
            outcome.issued.append(name)
            continue
        else:
            from .org_onboarding import issue_organization_credential

            credential = await issue_organization_credential(
                db,
                settings,
                owner,
                roles=list(participant.roles or []),
                allowed_scopes=list(participant.allowed_scopes or []),
                dsp_address=participant.dsp_address,
            )
            signed.append((name, credential.credential_json))
            outcome.issued.append(name)
            continue

    if not signed:
        return outcome

    endpoint = endpoint_of(service_endpoints(document), CREDENTIAL_SERVICE_TYPE)
    if not endpoint:
        outcome.error = (
            f"{did} publishes no {CREDENTIAL_SERVICE_TYPE} entry in its DID "
            "document, so there is nowhere to deliver its credentials"
        )
        return outcome

    try:
        await deliver(db, settings, did=did, endpoint=endpoint, credentials=signed)
        outcome.delivered_to = endpoint
    except IssuanceError as exc:
        outcome.error = exc.message

    return outcome


async def _active_credential(
    db: AsyncSession, did: str, credential_type: str
) -> Credential | None:
    return (
        await db.execute(
            select(Credential).where(
                Credential.subject_did == did,
                Credential.credential_type == credential_type,
                Credential.status == "active",
            )
        )
    ).scalars().first()


async def _membership_credentials(
    db: AsyncSession,
    settings: Settings,
    participant: Participant,
    anchor_did: str,
    ttl: int,
) -> list[tuple[dict, int]]:
    """One credential per role, and **its own StatusList index each**.

    Exactly what `participant add` produced. Collapsing them into one credential
    naming both roles would be a smaller register and a different claim: a role
    is what a membership attests, and revoking a provider role without revoking a
    consumer role has to remain expressible.
    """
    out: list[tuple[dict, int]] = []
    for role in list(participant.roles or []) or ["consumer"]:
        index = await allocate_status_list_index(db)
        out.append(
            (
                build_membership_credential(
                    issuer_did=anchor_did,
                    subject_did=participant.did,
                    role=role,
                    allowed_scopes=list(participant.allowed_scopes or []),
                    credentials_context_url=settings.credentials_context_url,
                    dataspace_uri=settings.dataspace_uri,
                    status_list_credential_url=settings.status_list_url(),
                    status_list_index=index,
                    credential_id=generate_credential_id(),
                    ttl_days=ttl,
                ),
                index,
            )
        )
    return out


async def deliver(
    db: AsyncSession,
    settings: Settings,
    *,
    did: str,
    endpoint: str,
    credentials: list[tuple[str, dict]],
    timeout: float = 10.0,
) -> None:
    """Write issued credentials to the holder's Storage API.

    CIP §Storage API: `POST {credentialService}/credentials`, a
    `CredentialMessage`, authenticated by **the issuer's own** Self-Issued ID
    token. The holder verifies that token against the issuer's DID document, so
    this is the same proof-of-control mechanism running in the other direction.

    `format: "json-ld"` and the whole signed VC object as `payload` — the spec's
    own example carries exactly that, and it means what arrives at the holder is
    byte-identical to what the issuer signed. Sending only the JWT would make the
    holder reconstruct the envelope, which is one more place for the two sides to
    disagree about what was issued.
    """
    token = await create_self_signed_token(
        db, settings, settings.trust_anchor_did, audience=did
    )
    message = {
        "@context": [DCP_CONTEXT],
        "type": "CredentialMessage",
        "issuerPid": settings.trust_anchor_did,
        "holderPid": did,
        "status": "ISSUED",
        "credentials": [
            {"credentialType": name, "payload": payload, "format": "json-ld"}
            for name, payload in credentials
        ],
    }
    url = f"{endpoint.rstrip('/')}/credentials"

    async with httpx.AsyncClient(timeout=timeout) as http:
        try:
            response = await http.post(
                url, json=message, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as exc:
            raise IssuanceError(f"could not deliver to {url}: {exc}") from exc

    if response.status_code >= 400:
        raise IssuanceError(
            f"{url} refused delivery ({response.status_code}): "
            f"{response.text.strip()[:200]}"
        )
    log.info(
        "Delivered %s to %s", ", ".join(name for name, _ in credentials), url
    )


async def store_delivered(
    db: AsyncSession,
    *,
    holder_did: str,
    issuer_did: str,
    credentials: list[dict],
) -> list[str]:
    """Holder side of the Storage API: keep what an issuer just wrote.

    Idempotent on credential id, because a redelivery after a timeout is the
    normal case and a duplicate row would double every presentation.
    """
    stored: list[str] = []
    for container in credentials:
        payload = container.get("payload")
        if not isinstance(payload, dict):
            # Only the JSON-LD form is accepted. A bare JWT would have to be
            # decoded and re-enveloped here to be presentable, and a holder that
            # rebuilds what an issuer signed is a holder that can disagree with
            # it.
            raise IssuanceError(
                "only format=json-ld with an object payload is accepted"
            )
        credential_id = payload.get("id")
        if not isinstance(credential_id, str) or not credential_id:
            raise IssuanceError("a delivered credential carries no id")

        existing = (
            await db.execute(select(Credential).where(Credential.id == credential_id))
        ).scalar_one_or_none()
        if existing is not None:
            existing.credential_json = payload
            stored.append(credential_id)
            continue

        types = payload.get("type") or []
        credential_type = next(
            (t for t in types if t != "VerifiableCredential"), "VerifiableCredential"
        )
        expires_at = None
        raw_expiry = payload.get("expirationDate") or payload.get("validUntil")
        if isinstance(raw_expiry, str):
            try:
                expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
            except ValueError:
                expires_at = None

        db.add(
            Credential(
                id=credential_id,
                credential_type=credential_type,
                issuer_did=issuer_did,
                subject_did=holder_did,
                credential_json=payload,
                # **No StatusList index.** The register is the issuer's; a holder
                # recording an index would imply it can revoke, which it cannot.
                status_list_index=None,
                expires_at=expires_at,
            )
        )
        stored.append(credential_id)

    await db.flush()
    return stored
