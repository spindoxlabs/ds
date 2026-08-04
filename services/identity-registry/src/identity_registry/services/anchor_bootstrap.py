"""Trust-anchor side of first-time setup — the mirror of `participant_bootstrap`.

One instance in the dataspace runs as `trust-anchor` and this is what it does
before it can do anything else: hold a signing key, publish a DID document that
says **where to enrol**, and list itself in its own trust list.

The asymmetry with the participant side is the only interesting part. A
participant publishes a `CredentialService` (and a DSP endpoint) because it is a
party you *talk to*; the anchor publishes an `IssuerService` because it is the
party you *ask for credentials*. Both are `service` entries of a `did:web`
document, which is what makes the whole handshake discoverable from one
identifier — `credential.issuance.protocol.md`, Issuer Service discovery.

**Idempotent, and it refreshes what it publishes.** This lived inline in
`ir-cli bootstrap` as an early return on "a DID already exists", which meant a
registry bootstrapped before the `IssuerService` entry existed would never
publish one however many times bootstrap ran — the fix would have to be a manual
`UPDATE`. Re-running now rewrites the service entries and leaves the key alone,
for the same reason as `participant_bootstrap.ensure_identity`: rotating a key on
a pod restart would silently invalidate every credential bound to it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Did, Key
from .crypto import encrypt_private_jwk, generate_key_pair

log = logging.getLogger(__name__)

#: CIP's name for the endpoint a `CredentialRequestMessage` is posted to.
ISSUER_SERVICE_TYPE = "IssuerService"


@dataclass(slots=True)
class AnchorIdentity:
    did: str
    kid: str
    created: bool
    service_endpoints: list[dict[str, str]]


def issuer_service_entry(settings: Settings) -> dict[str, str]:
    """Where credential requests go, as a DID document `service` entry.

    The base URL, not the full path: a client appends CIP's own
    `/credentials` (request) and `/requests/{id}` (status). Publishing the full
    request path would work today and hardcode one of the two endpoints CIP
    defines under this base.

    Without this entry a client has to be *told* where to enrol out of band —
    which works, and is exactly the side-channel a resolvable identifier exists
    to remove.
    """
    return {
        "type": ISSUER_SERVICE_TYPE,
        "serviceEndpoint": f"{settings.public_base_url.rstrip('/')}/issuer",
    }


async def ensure_identity(
    db: AsyncSession, settings: Settings, *, did: str | None = None
) -> AnchorIdentity:
    """Generate and hold the anchor's signing key, and publish its document.

    Does not commit — the caller owns the transaction, because bootstrap also
    seeds the trust list and the two belong in one unit: an anchor with a key and
    no accreditation publishes a list saying it accredits nobody, and every
    credential it goes on to issue reads as coming from an unlisted issuer.
    """
    did = did or f"did:web:{settings.trust_anchor_domain}"
    endpoints = [issuer_service_entry(settings)]

    key = (
        await db.execute(select(Key).where(Key.owner_did == did, Key.active.is_(True)))
    ).scalar_one_or_none()
    created = key is None
    if key is None:
        kp = generate_key_pair(did)
        key = Key(
            owner_did=did,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
            public_jwk=kp.public_jwk,
        )
        db.add(key)
        await db.flush()

    did_row = (await db.execute(select(Did).where(Did.did == did))).scalar_one_or_none()
    if did_row is None:
        db.add(
            Did(
                did=did,
                did_type="participant",
                display_name="Trust Anchor",
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

    return AnchorIdentity(
        did=did, kid=key.kid, created=created, service_endpoints=endpoints
    )
