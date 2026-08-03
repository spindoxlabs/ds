"""The dataspace's trust list — who this dataspace accepts attestations from.

`DSSC-TRF-05`, `-07`, `-17`, `DSSC-BIZ-143`, `CEEDS-ARC-34`.

**The first thing a stranger reads about us.** Everything else in the identity
chain answers *"is this credential valid"*; this answers the question underneath
it — *"is its issuer somebody this dataspace accredited, and for what"*. A
verifier that cannot ask that has to hardcode an issuer DID, which is what the
connector does today by reading the anchor's public key from a mounted file (see
`DID-17`): fine while there is one issuer, and unrotatable the moment there is a
second or the first changes key.

Published unauthenticated for the same reason the revocation list is: a
counterparty must be able to read it **before** it has any relationship with this
dataspace, and a federation partner reads it before anything else.

## Three things the shape has to get right, and each is easy to miss

**Revoked entries stay listed** (`TRF-05` says so explicitly). A trust list that
forgets what it used to trust cannot answer *"was this credential legitimate when
it was issued"* — which is the question a verifier has about everything already
in circulation. Dropping the row would silently re-open every past credential.

**Every entry names its scope of attestation** (`TRF-19`). An entry with no scope
does not mean "trusted for everything"; it means an entry nobody should rely on,
and the published document says that in words rather than leaving an empty list
to be read as a wildcard.

**Authority is a field, not a hierarchy** (`TRF-21`, `-25`, `-26`): a trust
service provider derives authority *from* an anchor, many services may serve one
anchor and one service may serve many. A nested tree would make the common case
tidy and the specified case unrepresentable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import TrustedIssuer

TRUST_ANCHOR = "trust-anchor"
TRUST_SERVICE_PROVIDER = "trust-service-provider"

VALID_ROLES = frozenset({TRUST_ANCHOR, TRUST_SERVICE_PROVIDER})

#: What this deployment's own anchor is accredited to attest. Seeded, not
#: inferred: the anchor issues these three because the rulebook says it does
#: (`participation.md` §3), and a list that read the types out of whatever had
#: been issued would grow silently.
ANCHOR_SCOPE = (
    "MembershipCredential",
    "OrganizationCredential",
    "DataSubjectCredential",
)


class TrustListError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class Entry:
    did: str
    name: str
    role: str
    scope_of_attestation: list[str]
    status: str
    derives_authority_from: str | None
    added_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None


async def ensure_own_anchor(
    db: AsyncSession, settings: Settings, *, name: str | None = None
) -> TrustedIssuer:
    """Seed this deployment's own trust anchor. Idempotent.

    Called from `ir-cli bootstrap`, because a dataspace whose trust list does not
    contain its own anchor publishes a document saying it accredits nobody — and
    every credential it has issued would read as coming from an unlisted issuer.
    """
    did = settings.trust_anchor_did
    existing = (
        await db.execute(select(TrustedIssuer).where(TrustedIssuer.did == did))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    entry = TrustedIssuer(
        did=did,
        name=name or "Trust anchor",
        role=TRUST_ANCHOR,
        scope_of_attestation=list(ANCHOR_SCOPE),
        status="active",
        added_by="bootstrap",
    )
    db.add(entry)
    await db.flush()
    return entry


async def add_issuer(
    db: AsyncSession,
    *,
    did: str,
    name: str,
    role: str,
    scope_of_attestation: list[str],
    derives_authority_from: str | None = None,
    added_by: str | None = None,
) -> TrustedIssuer:
    if role not in VALID_ROLES:
        raise TrustListError(
            f"role must be one of {sorted(VALID_ROLES)}", status_code=422
        )
    if not scope_of_attestation:
        # Refused rather than defaulted. An entry with no scope is not "trusted
        # for everything" and must not be creatable by omission — `TRF-19`.
        raise TrustListError(
            "an entry must name its scope of attestation: what this entity is "
            "accredited to attest (DSSC-TRF-19). An empty scope is not a "
            "wildcard, and a list that let it be one would be unreadable.",
            status_code=422,
        )
    if role == TRUST_SERVICE_PROVIDER and not derives_authority_from:
        raise TrustListError(
            "a trust service provider derives its authority from a trust anchor "
            "(DSSC-TRF-21) — name it.",
            status_code=422,
        )

    existing = (
        await db.execute(select(TrustedIssuer).where(TrustedIssuer.did == did))
    ).scalar_one_or_none()
    if existing is not None:
        raise TrustListError(f"{did} is already listed", status_code=409)

    entry = TrustedIssuer(
        did=did,
        name=name,
        role=role,
        scope_of_attestation=list(scope_of_attestation),
        derives_authority_from=derives_authority_from,
        status="active",
        added_by=added_by,
    )
    db.add(entry)
    await db.flush()
    return entry


async def revoke_issuer(
    db: AsyncSession, did: str, *, reason: str
) -> TrustedIssuer:
    """Mark an entry revoked. **Never deletes it** — `TRF-05`."""
    entry = (
        await db.execute(select(TrustedIssuer).where(TrustedIssuer.did == did))
    ).scalar_one_or_none()
    if entry is None:
        raise TrustListError(f"{did} is not listed", status_code=404)
    if entry.status == "revoked":
        return entry
    entry.status = "revoked"
    entry.revoked_at = datetime.now(UTC)
    entry.revocation_reason = reason
    await db.flush()
    return entry


async def entries(db: AsyncSession) -> list[Entry]:
    rows = (
        await db.execute(select(TrustedIssuer).order_by(TrustedIssuer.did))
    ).scalars().all()
    return [
        Entry(
            did=r.did,
            name=r.name,
            role=r.role,
            scope_of_attestation=list(r.scope_of_attestation or []),
            status=r.status,
            derives_authority_from=r.derives_authority_from,
            added_at=r.added_at,
            revoked_at=r.revoked_at,
            revocation_reason=r.revocation_reason,
        )
        for r in rows
    ]


def render(entries_: list[Entry], settings: Settings) -> dict[str, Any]:
    """The published document.

    Self-describing on purpose. DSSC names no format for this list, so a reader
    from another dataspace gets the requirement ids it satisfies and a
    `dataspace` it belongs to — enough to tell what they are holding without
    having read our rulebook first.

    Each entry carries the URL its key resolves at. That is not decoration: it is
    what lets a verifier check a signature against the issuer's **DID document**
    rather than a key somebody handed it, which is the same rule `P-8a` states
    for presentation queries.
    """
    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "type": "DataspaceTrustList",
        "dataspace": settings.dataspace_uri,
        "conformsTo": ["DSSC-TRF-05", "DSSC-TRF-07", "DSSC-TRF-17"],
        "retrievedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issuers": [
            {
                "id": e.did,
                "name": e.name,
                "role": e.role,
                # `TRF-19` — accepted in relation to a specific scope.
                "scopeOfAttestation": e.scope_of_attestation,
                "status": e.status,
                **(
                    {"derivesAuthorityFrom": e.derives_authority_from}
                    if e.derives_authority_from
                    else {}
                ),
                **(
                    {
                        "revokedAt": e.revoked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "revocationReason": e.revocation_reason,
                    }
                    if e.status == "revoked" and e.revoked_at
                    else {}
                ),
                "didDocument": f"{settings.public_base_url}/dids/{e.did}/did.json",
            }
            for e in entries_
        ],
    }
