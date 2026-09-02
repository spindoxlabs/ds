"""VP building — constructs Verifiable Presentations for DCP credential queries.

What a presentation may contain is bounded twice: by what the verifier **asked
for** (the query's ``scope`` or ``presentationDefinition``) and by what its
access token was **granted**. The intersection is what ships.

Before this, neither bound applied: the query's scope was not read at all and no
grant existed, so an empty presentation definition — which is exactly what EDC
sends — returned every active credential the participant held.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models import Credential, Key
from .crypto import (
    create_jws,
    decrypt_private_jwk,
    load_private_key,
    require_private_jwk,
)

#: The scope alias DCP implementations agree on. Upstream's
#: `EdcScopeToCriterionTransformer` rejects anything else, so accepting a second
#: spelling here would make this registry answer requests no other credential
#: service would.
SCOPE_ALIAS = "org.eclipse.dspace.dcp.vc.type"

#: Operations that mean "may read this credential type".
SCOPE_OPERATIONS = frozenset({"read", "all", "*"})


class ScopeInvalid(Exception):
    """A scope string is not a DCP credential-type scope."""


def parse_credential_scope(scope: str) -> str:
    """``…vc.type:MembershipCredential:read`` → ``MembershipCredential``.

    The discriminator may be context-qualified (``<context>#Type``), in which
    case the type is what follows the last ``#`` — same rule as upstream.
    """
    first = scope.find(":")
    last = scope.rfind(":")
    if first == -1 or first == last:
        raise ScopeInvalid(f"malformed scope: {scope}")

    alias, discriminator, operation = (
        scope[:first],
        scope[first + 1 : last],
        scope[last + 1 :],
    )
    if alias.lower() != SCOPE_ALIAS:
        raise ScopeInvalid(f"scope alias must be {SCOPE_ALIAS}, got {alias}")
    if operation not in SCOPE_OPERATIONS:
        raise ScopeInvalid(f"invalid scope operation: {operation}")
    if not discriminator:
        raise ScopeInvalid(f"scope names no credential type: {scope}")
    return discriminator.rsplit("#", 1)[-1]


def credential_types_for(scopes: list[str]) -> set[str]:
    """Credential types named by *scopes*, skipping ones that name none.

    A scope this service cannot parse is dropped rather than fatal: the DCP
    specification says a query carrying scopes the client is not entitled to
    returns fewer presentations, not an error.
    """
    types: set[str] = set()
    for scope in scopes:
        try:
            types.add(parse_credential_scope(scope))
        except ScopeInvalid:
            continue
    return types


def types_from_presentation_definition(
    presentation_definition: dict[str, Any],
) -> set[str]:
    types: set[str] = set()
    for desc in presentation_definition.get("input_descriptors", []):
        for constraint in (desc.get("constraints") or {}).get("fields", []):
            if "$.type" in constraint.get("path", []):
                filter_spec = constraint.get("filter") or {}
                for filt in filter_spec.get("contains", {}).get("const", []):
                    types.add(filt)
    return types


async def build_presentation_response(
    db: AsyncSession,
    participant_did: str,
    *,
    granted_types: set[str],
    requested_types: set[str] | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    """Build a DCP PresentationResponseMessage containing a VP JWT.

    *granted_types* is what the access token allows and is always applied.
    *requested_types* narrows further when the query named specific types; an
    empty request means "everything I am entitled to", which is what EDC sends.
    """
    key_result = await db.execute(
        select(Key).where(
            Key.owner_did == participant_did,
            Key.active.is_(True),
        )
    )
    key = key_result.scalar_one_or_none()
    if not key:
        raise LookupError(f"No active key for participant: {participant_did}")

    selected = granted_types if not requested_types else granted_types & requested_types

    cred_result = await db.execute(
        select(Credential).where(
            Credential.subject_did == participant_did,
            Credential.status == "active",
        )
    )
    credentials = [
        row.credential_json
        for row in cred_result.scalars().all()
        if selected & set(row.credential_json.get("type", []))
    ]

    vc_tokens = [
        vc["proof"]["jws"]
        for vc in credentials
        if isinstance(vc.get("proof"), dict) and vc["proof"].get("jws")
    ]

    settings = get_settings()
    raw_jwk = decrypt_private_jwk(
        require_private_jwk(
            key.private_jwk, kid=key.kid, purpose="sign a verifiable presentation"
        ),
        settings.encryption_key,
    )
    private_key = load_private_key(raw_jwk)
    now = int(time.time())

    vp_claims: dict[str, Any] = {
        "iss": participant_did,
        "sub": participant_did,
        "nbf": now,
        "iat": now,
        "exp": now + 300,
        "jti": str(uuid.uuid4()),
        "vp": {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "holder": participant_did,
            "verifiableCredential": vc_tokens,
        },
    }
    if audience:
        # The verifier checks that the presentation was made *to it*. Without
        # this, a VP captured from one exchange is replayable into another.
        vp_claims["aud"] = audience

    vp_jwt = create_jws({"alg": "ES256", "kid": key.kid}, vp_claims, private_key)

    return {
        # DCP v1.0, and it has to be exactly this IRI. A verifier expands this
        # document and looks for `<namespace>presentation`; under the old
        # `tractusx-trust/v0.8` namespace the property expanded to something EDC
        # 0.16 does not read, so the response parsed cleanly into **zero**
        # presentations and the counterparty reported *"Number of requested
        # credentials does not match the number of returned credentials"* — a
        # complete, correctly-signed VP, discarded on the term alone.
        #
        # The namespace is inlined rather than referenced as a remote context
        # (`https://w3id.org/dspace-dcp/v1.0/dcp.jsonld`) on purpose: expansion
        # then needs no fetch and no cache hit at the far end, which is one less
        # thing between a signature and the decision it supports.
        "@context": {
            "dcp": "https://w3id.org/dspace-dcp/v1.0/",
        },
        "@type": "dcp:PresentationResponseMessage",
        "dcp:presentation": {
            "@value": [vp_jwt],
            "@type": "@json",
        },
    }
