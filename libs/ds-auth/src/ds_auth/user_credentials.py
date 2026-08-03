"""User Verifiable Credential verification for portal-facing APIs.

The signing key comes from the **issuer's DID document**, resolved over did:web
(`DID-17`). It used to come from a file this service mounted, which is the `P-8a`
class — *never against a key this deployment happens to hold* — and meant that
rotating the trust anchor's key required redeploying every service holding a copy.

Two questions, asked in this order and neither sufficient alone:

1. **Is this signature from the key that DID publishes?** Resolve the document,
   select the method the `kid` names, verify.
2. **Is that DID one this dataspace accredited?** The issuer is pinned to the
   configured trust anchor, and where a trust-list URL is configured the entry
   must be **active** — `DSSC-TRF-05`. A key that resolves proves authorship and
   says nothing about authority.

Step 1 reads `iss` out of an **unverified** payload to know whose document to
fetch, which is safe only because step 2's first half happens before it: an `iss`
that is not the configured issuer is refused without resolving anything. Without
that ordering, anyone could name their own DID as issuer and sign with their own
key.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import HTTPException

from .did_web import (
    DidResolutionError,
    DidWebResolver,
    assertion_jwk,
    public_key_from_jwk,
)

log = logging.getLogger(__name__)

#: One resolver per process, so its cache is shared across requests. Configured
#: on first use from whatever the caller passes; a service has exactly one
#: did:web scheme and one TTL.
_RESOLVER: DidWebResolver | None = None


def get_resolver(
    *, use_https: bool = True, ttl_seconds: float | None = None
) -> DidWebResolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = DidWebResolver(
            use_https=use_https,
            **({"ttl_seconds": ttl_seconds} if ttl_seconds is not None else {}),
        )
    return _RESOLVER


def reset_resolver() -> None:
    """Drop the process-wide resolver. For tests and for key rotation."""
    global _RESOLVER
    _RESOLVER = None


@dataclass(frozen=True)
class UserCredential:
    did: str
    subject_id: str
    role: str
    issuer: str
    linked_participant: str | None = None


def _b64url_decode(value: str) -> bytes:
    padding = 4 - len(value) % 4
    return base64.urlsafe_b64decode(value + "=" * (padding % 4))


def verify_user_vc_jwt(
    token: str | None,
    expected_subject_id: str | None,
    trust_anchor_did: str | None,
    required_roles: set[str] | None = None,
    *,
    trust_list_url: str | None = None,
    did_web_use_https: bool = True,
    did_cache_ttl_seconds: float | None = None,
    expected_linked_participant: str | None = None,
    credential_status_path: str | None = None,
    credential_status_url: str | None = None,
    insecure_dev: bool = False,
    resolver: DidWebResolver | None = None,
) -> UserCredential:
    if not token:
        raise HTTPException(
            401, "Missing user Verifiable Credential (X-User-VC header)"
        )
    if not expected_subject_id:
        raise HTTPException(401, "Missing subject identity (X-Subject-Id header)")

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(401, "Invalid user Verifiable Credential format")
    try:
        header: dict[str, Any] = json.loads(_b64url_decode(parts[0]))
    except Exception as exc:
        raise HTTPException(401, "Invalid user Verifiable Credential header") from exc
    if header.get("alg") != "ES256":
        raise HTTPException(401, "Unsupported user Verifiable Credential algorithm")

    payload: dict[str, Any] = json.loads(_b64url_decode(parts[1]))
    vc = payload.get("vc") or {}
    claimed_issuer = str(payload.get("iss") or vc.get("issuer") or "")

    # **One switch, one meaning.** `insecure_dev` skips signature verification —
    # that and nothing else. It used to be implied by *the absence of a mounted
    # key*, so a deployment that forgot the mount and left the flag at its
    # permissive default silently accepted unverified credentials while looking
    # configured. There is no longer a way to reach the unsigned path by
    # omission: it is one boolean, and `ProductionGuard` forbids it being true.
    if insecure_dev:
        log.warning(
            "Accepting user Verifiable Credential WITHOUT signature verification "
            "(VC_INSECURE_DEV=true). Local development only."
        )
    elif not trust_anchor_did:
        # Nothing to resolve, so nothing to verify against — and every
        # downstream ownership check reads its subject from this payload.
        log.error(
            "No trust-anchor DID is configured — refusing to accept an "
            "unverified user Verifiable Credential."
        )
        raise HTTPException(503, "User credential verification is not configured")
    else:
        # **Before resolving anything.** The document to fetch is named by an
        # unverified claim, so an issuer this deployment does not trust must be
        # refused here — otherwise a stranger names their own DID as `iss` and
        # this happily verifies their signature against their own key.
        if claimed_issuer != trust_anchor_did:
            raise HTTPException(403, "User VC issuer is not trusted")

        signing_input = f"{parts[0]}.{parts[1]}".encode()
        signature = _b64url_decode(parts[2])
        if len(signature) != 64:
            raise HTTPException(401, "Invalid user Verifiable Credential signature")

        resolver = resolver or get_resolver(
            use_https=did_web_use_https, ttl_seconds=did_cache_ttl_seconds
        )
        try:
            document = resolver.resolve(trust_anchor_did)
            if trust_list_url:
                # Authority, not authorship — `DSSC-TRF-05`. An issuer whose
                # accreditation was withdrawn still holds its key and still
                # signs valid credentials; the list is the only thing that says
                # so, and revoked entries stay listed precisely to be read here.
                resolver.accredited(
                    trust_list_url,
                    trust_anchor_did,
                    credential_type=_credential_type(vc),
                )
            public_key = public_key_from_jwk(
                assertion_jwk(document, header.get("kid"))
            )
        except DidResolutionError as exc:
            log.error("cannot verify user credential: %s", exc)
            raise HTTPException(
                503, f"Issuer identity could not be established: {exc}"
            ) from exc

        der_signature = encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        try:
            public_key.verify(der_signature, signing_input, ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise HTTPException(
                401, "Invalid user Verifiable Credential signature"
            ) from exc

    subject = vc.get("credentialSubject") or {}
    subject_id = str(subject.get("id") or payload.get("sub") or "")
    role = str(subject.get("role") or "")
    did = str(subject.get("id") or payload.get("sub") or "")
    issuer = claimed_issuer
    linked_participant = subject.get("linkedParticipant")
    now = datetime.now(UTC).timestamp()

    if subject_id != expected_subject_id:
        raise HTTPException(403, "User VC subject does not match authenticated subject")
    # Re-stated for the `insecure_dev` path, which resolves nothing and so has
    # not passed the check above. On the verified path this is the same
    # comparison a second time, and cheaper than a branch that could drift.
    if trust_anchor_did and issuer != trust_anchor_did:
        raise HTTPException(403, "User VC issuer is not trusted")
    if vc.get("issuer") and vc.get("issuer") != issuer:
        raise HTTPException(403, "User VC issuer claim mismatch")
    if payload.get("sub") and payload.get("sub") != did:
        raise HTTPException(403, "User VC subject DID claim mismatch")
    if not did.startswith("did:web:"):
        raise HTTPException(403, "User VC subject must be a did:web identifier")
    if (
        expected_linked_participant
        and linked_participant != expected_linked_participant
    ):
        raise HTTPException(403, "User VC is not linked to this participant")
    if payload.get("nbf") is not None and float(payload["nbf"]) > now:
        raise HTTPException(401, "User VC is not valid yet")
    if payload.get("exp") is not None and float(payload["exp"]) <= now:
        raise HTTPException(401, "User VC has expired")
    if required_roles and role not in required_roles:
        raise HTTPException(403, f"User VC role {role!r} is not allowed")
    if credential_status_url or credential_status_path:
        _verify_credential_status(vc, credential_status_path, credential_status_url)

    return UserCredential(
        did=did,
        subject_id=subject_id,
        role=role,
        issuer=issuer,
        linked_participant=str(linked_participant) if linked_participant else None,
    )


def _credential_type(vc: dict[str, Any]) -> str | None:
    """The specific type of a VC, for the trust list's scope check.

    `type` is `["VerifiableCredential", "DataSubjectCredential"]` — the first
    entry is the base type every credential carries and says nothing about what
    was attested, so the scope check reads the *other* one. No specific type
    means no scope claim to check, not a wildcard.
    """
    types = vc.get("type")
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        return None
    specific = [t for t in types if isinstance(t, str) and t != "VerifiableCredential"]
    return specific[0] if len(specific) == 1 else None


def _verify_credential_status(
    vc: dict[str, Any],
    credential_status_path: str | None = None,
    credential_status_url: str | None = None,
) -> None:
    status = vc.get("credentialStatus")
    if not isinstance(status, dict):
        raise HTTPException(401, "User VC has no credentialStatus")

    status_list = _load_credential_status_list(
        credential_status_path, credential_status_url
    )

    entry = (status_list.get("credentials") or {}).get(vc.get("id"))
    if not isinstance(entry, dict):
        raise HTTPException(401, "User VC is not present in credential status list")
    if entry.get("status") != "active":
        raise HTTPException(401, "User VC is not active")


def _load_credential_status_list(
    credential_status_path: str | None,
    credential_status_url: str | None,
) -> dict[str, Any]:
    if credential_status_url:
        try:
            req = Request(credential_status_url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise HTTPException(
                503, "Credential status registry is not available"
            ) from exc

    if not credential_status_path:
        raise HTTPException(503, "Credential status registry is not configured")

    path = Path(credential_status_path)
    if not path.exists():
        raise HTTPException(503, "Credential status list is not available")
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise HTTPException(503, "Credential status list is invalid") from exc
