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
import gzip
import json
import logging
import threading
import time
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import HTTPException

from .address_guard import InternalAllowance
from .did_web import (
    DidResolutionError,
    DidWebResolver,
    assertion_jwk,
    public_key_from_jwk,
)
from .production import is_production

log = logging.getLogger(__name__)

#: One resolver per process, so its cache is shared across requests. Configured
#: on first use from whatever the caller passes; a service has exactly one
#: did:web scheme and one TTL.
_RESOLVER: DidWebResolver | None = None


def get_resolver(
    *,
    use_https: bool = True,
    ttl_seconds: float | None = None,
    allowance: InternalAllowance | None = None,
) -> DidWebResolver:
    """The process-wide resolver. ``allowance`` is the service's ADR-0029
    allowance (`<PREFIX>_DID_WEB_INTERNAL_HOSTS` / `_NETWORKS`); a service has
    exactly one, so the first call's is the resolver's."""
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = DidWebResolver(
            use_https=use_https,
            allowance=allowance,
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


def _es256_verifies(parts: list[str], public_key: Any) -> bool:
    """Whether a compact JWS's raw ES256 signature verifies against *public_key*.

    One implementation for the two things signed by the trust anchor that this
    module reads: the user credential and its status register.
    """
    signature = _b64url_decode(parts[2])
    if len(signature) != 64:
        return False
    der_signature = encode_dss_signature(
        int.from_bytes(signature[:32], "big"),
        int.from_bytes(signature[32:], "big"),
    )
    try:
        public_key.verify(
            der_signature,
            f"{parts[0]}.{parts[1]}".encode(),
            ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        return False
    return True


def verify_user_vc_jwt(
    token: str | None,
    expected_subject_id: str | None,
    trust_anchor_did: str | None,
    required_roles: set[str] | None = None,
    *,
    trust_list_url: str | None = None,
    did_web_use_https: bool = True,
    did_cache_ttl_seconds: float | None = None,
    did_web_allowance: InternalAllowance | None = None,
    expected_linked_participant: str | None = None,
    credential_status_path: str | None = None,
    credential_status_url: str | None = None,
    insecure_dev: bool = False,
    resolver: DidWebResolver | None = None,
    status_cache_ttl_seconds: float | None = None,
    require_credential_status: bool | None = None,
) -> UserCredential:
    """Verify a user credential and return who it names.

    ``require_credential_status`` says whether a credential may be accepted with
    **no** status source configured. ``None`` (the default) reads the posture:
    required everywhere except ``DS_ENV=dev``. Outside dev a credential whose
    revocation cannot be checked is a 503, never an accept — a verifier that
    does not read the register cannot see a revocation, so the issuer's only way
    to withdraw a credential would silently stop working.
    """
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

        resolver = resolver or get_resolver(
            use_https=did_web_use_https,
            ttl_seconds=did_cache_ttl_seconds,
            allowance=did_web_allowance,
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
            public_key = public_key_from_jwk(assertion_jwk(document, header.get("kid")))
        except DidResolutionError as exc:
            log.error("cannot verify user credential: %s", exc)
            raise HTTPException(
                503, f"Issuer identity could not be established: {exc}"
            ) from exc

        if not _es256_verifies(parts, public_key):
            raise HTTPException(401, "Invalid user Verifiable Credential signature")

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
    # **`exp` is required, not merely honoured.** A credential with no expiry
    # never lapses: if the status register is ever unreadable, misconfigured or
    # skipped, nothing else bounds how long a leaked one stays usable. The
    # identity-registry sets it on everything it signs (`sign_credential`), so
    # this refuses only a credential no issuer of ours produced.
    exp = payload.get("exp")
    if exp is None:
        raise HTTPException(401, "User VC has no expiry")
    try:
        expires_at = float(exp)
    except (TypeError, ValueError):
        raise HTTPException(401, "User VC has an unreadable expiry") from None
    if expires_at <= now:
        raise HTTPException(401, "User VC has expired")
    if required_roles and role not in required_roles:
        raise HTTPException(403, f"User VC role {role!r} is not allowed")

    if require_credential_status is None:
        require_credential_status = is_production()
    if credential_status_url or credential_status_path:
        _verify_credential_status(
            vc,
            credential_status_path,
            credential_status_url,
            issuer=issuer,
            verify_signature=not insecure_dev,
            resolver=resolver
            or get_resolver(
                use_https=did_web_use_https,
                ttl_seconds=did_cache_ttl_seconds,
                allowance=did_web_allowance,
            ),
            ttl_seconds=status_cache_ttl_seconds,
        )
    elif require_credential_status:
        # Outside dev a credential whose revocation cannot be checked is not a
        # credential this service may accept. `ProductionGuard` refuses to start
        # without the setting; this is the same rule at the point of use, for a
        # caller that builds no guard.
        log.error(
            "No credential status source is configured — refusing a user "
            "credential whose revocation cannot be checked."
        )
        raise HTTPException(503, "User credential status checking is not configured")
    else:
        log.warning(
            "Accepting a user Verifiable Credential WITHOUT a revocation check "
            "(no *_CREDENTIAL_STATUS_URL; DS_ENV=dev). Local development only."
        )

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


# ── The credential status registers ───────────────────────────────
#
# Bitstring Status List (and StatusList2021, its predecessor), read the way the
# specifications define it: a credential names one register per `statusPurpose`,
# each entry naming the list credential to fetch and the **bit index** inside it
# that refers to this credential. The register publishes a GZIP-compressed
# bitstring — multibase base64url (`u…`) for Bitstring Status List, plain base64
# in StatusList2021 lists — and the bit at that index, counted from the left, is
# the answer.
#
# The identity-registry issues `BitstringStatusListEntry` since R3 and serves
# its registers as `BitstringStatusListCredential`. Credentials issued before
# carry `StatusList2021Entry` naming the **same** register URL and index, so both
# entry types are read against whichever list type the register now publishes.
#
# This used to read its source as a bespoke `{"credentials": {<id>: {"status":
# …}}}` lookup map, which no issuer anywhere emits — least of all ours. The
# provisioning bundle hands a new participant `{ir}/status/1`, that endpoint
# serves a StatusList2021 credential, and the two shapes have nothing in common,
# so a deployment that wired the value it was handed refused **every** user
# credential with "not present in credential status list" — a message about an
# unknown credential when what had happened was that the reader could not
# understand the document (ds#32). Nothing caught it because the only fixture
# wrote the bespoke shape by hand: both ends of the assertion were ours, and
# they agreed with each other and with nothing else.
#
# Reading the real format is also what makes the second register worth having.
# The identity-registry issues every credential with two entries on one mirrored
# index — revocation and suspension — precisely so a verifier can tell
# *superseded* from *withdrawn* (`P-27`). A lookup map cannot express that; a
# bit on the register that was set can.

#: What a set bit means, per `statusPurpose`. A purpose we do not have a phrase
#: for still refuses — an unrecognised register is not a register to ignore.
_STATUS_REFUSAL = {
    "revocation": "User VC has been revoked",
    "suspension": "User VC is suspended",
}


#: The entry types this reader understands. They carry the same three fields
#: (`statusPurpose`, `statusListIndex`, `statusListCredential`), which is why one
#: reader serves both. Anything else is **refused**: EDC 0.18.0 logs an unknown
#: type and passes the credential (`RevocationServiceRegistryImpl`), which is a
#: credential nobody checked being accepted as one that was.
_SUPPORTED_ENTRY_TYPES = frozenset({"StatusList2021Entry", "BitstringStatusListEntry"})

#: The credential types a register may be published as.
_STATUS_LIST_TYPES = frozenset(
    {"StatusList2021Credential", "BitstringStatusListCredential"}
)

#: How long a verified register is reused, by default. EDC's
#: `edc.iam.credential.revocation.cache.validity` defaults to the same 15
#: minutes. It is the **revocation latency**: a credential revoked now is still
#: accepted by a process that read the register up to this long ago. Each
#: service exposes it as `*_CREDENTIAL_STATUS_CACHE_SECONDS`.
DEFAULT_STATUS_CACHE_SECONDS = 900.0

#: url -> (monotonic expiry, verified register document). Process-wide, like the
#: DID resolver: two requests naming the same register share one fetch.
_STATUS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_STATUS_LOCK = threading.Lock()


def reset_status_cache() -> None:
    """Drop every cached register. For tests, and to see a revocation now."""
    with _STATUS_LOCK:
        _STATUS_CACHE.clear()


def _verify_credential_status(
    vc: dict[str, Any],
    credential_status_path: str | None = None,
    credential_status_url: str | None = None,
    *,
    issuer: str | None = None,
    verify_signature: bool = True,
    resolver: DidWebResolver | None = None,
    ttl_seconds: float | None = None,
) -> None:
    """Refuse a credential whose bit is set on any register it names.

    **One entry or several.** A credential naming both the revocation and the
    suspension register carries a *list*, which is what every credential this
    dataspace issues has done since people became suspendable, and what
    StatusList2021 and Bitstring Status List both allow. Every usable entry is
    checked, not just the first: a credential is invalid if *any* register says
    so, which is also what EDC's `RevocationServiceRegistryImpl` does.

    **The entry type is read, not asserted.** `StatusList2021Entry` and
    `BitstringStatusListEntry` carry the same three fields this needs, so the
    profile move (`vcdm-2-0-profile-move`) does not have to come back through
    here.
    """
    status = vc.get("credentialStatus")
    raw = status if isinstance(status, list) else [status]
    entries = [entry for entry in raw if isinstance(entry, dict)]
    if not entries:
        raise HTTPException(401, "User VC has no credentialStatus")

    # One document per URL per credential. A credential naming two registers on
    # one host is two fetches; naming the same register twice is one.
    fetched: dict[str, dict[str, Any]] = {}
    checked = 0

    for entry in entries:
        entry_type = entry.get("type")
        if entry_type not in _SUPPORTED_ENTRY_TYPES:
            raise HTTPException(
                401, f"User VC credentialStatus type {entry_type!r} is not supported"
            )
        purpose = str(entry.get("statusPurpose") or "revocation")
        index = _status_list_index(entry)

        if credential_status_url:
            document = _fetch_status_list(
                _status_list_url(entry, credential_status_url),
                fetched,
                issuer=issuer,
                verify_signature=verify_signature,
                resolver=resolver,
                ttl_seconds=ttl_seconds,
            )
            published = _published_purpose(document)
            # EDC refuses this too, and for the same reason: a register read
            # under the wrong meaning answers a question nobody asked. A
            # revocation bit found on a list published as suspension does not
            # say the holder is suspended, it says the credential points at the
            # wrong list.
            if published != purpose:
                raise HTTPException(
                    401,
                    f"User VC names a {purpose!r} register that publishes "
                    f"{published or 'no'} statusPurpose",
                )
        else:
            # **A file is one register, so it answers for one purpose.** An
            # entry the file does not publish is left *unchecked* rather than
            # passed — and the tally below refuses the credential outright if
            # that was true of every entry. Checking revocation offline with no
            # local suspension register is a real state; knowing nothing and
            # returning success is not.
            document = _read_status_list(credential_status_path)
            if _published_purpose(document) != purpose:
                continue

        if _status_bit(document, index):
            raise HTTPException(
                401, _STATUS_REFUSAL.get(purpose, f"User VC status {purpose!r} is set")
            )
        checked += 1

    if not checked:
        raise HTTPException(
            503, "User VC status could not be checked against any known register"
        )


def status_bit_set(
    vc: dict[str, Any],
    purpose: str,
    *,
    register_origin: str,
    issuer: str | None = None,
    resolver: DidWebResolver | None = None,
    verify_signature: bool = True,
    ttl_seconds: float | None = None,
) -> bool | None:
    """Whether the register *vc* names for *purpose* has its bit set.

    ``None`` when the credential names no register for that purpose. The
    register is read exactly as `_verify_credential_status` reads one — the
    issuer's signed VC-JWT, verified, cached — from *register_origin* (scheme
    and host this caller is configured to reach) and the path the credential
    names. For a **holder** asking about a credential it keeps, rather than a
    verifier admitting one: the same failures raise the same ``HTTPException``,
    and a caller treats any of them as "unknown", never as "not set".
    """
    status = vc.get("credentialStatus")
    raw = status if isinstance(status, list) else [status]
    entries = [
        e
        for e in raw
        if isinstance(e, dict)
        and e.get("type") in _SUPPORTED_ENTRY_TYPES
        and str(e.get("statusPurpose") or "revocation") == purpose
    ]
    if not entries:
        return None
    origin = urlsplit(register_origin)
    fetched: dict[str, dict[str, Any]] = {}
    for entry in entries:
        named = urlsplit(str(entry.get("statusListCredential") or ""))
        if not named.path:
            raise HTTPException(503, "Credential names no status register")
        url = named._replace(scheme=origin.scheme, netloc=origin.netloc).geturl()
        document = _fetch_status_list(
            url,
            fetched,
            issuer=issuer,
            verify_signature=verify_signature,
            resolver=resolver,
            ttl_seconds=ttl_seconds,
        )
        if _published_purpose(document) != purpose:
            raise HTTPException(503, "Credential names a register of another purpose")
        if _status_bit(document, _status_list_index(entry)):
            return True
    return False


def _status_list_index(entry: dict[str, Any]) -> int:
    """The bit this credential occupies. A string per the specification, and an
    integer in the wild; both are accepted and nothing else is.

    Refused rather than defaulted to 0 — index 0 is a real credential, and
    reading somebody else's bit is worse than refusing to read one.
    """
    raw = entry.get("statusListIndex")
    try:
        index = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(
            401, "User VC credentialStatus has no usable statusListIndex"
        ) from None
    if index < 0:
        raise HTTPException(401, "User VC credentialStatus has a negative index")
    return index


def _status_list_url(entry: dict[str, Any], configured: str) -> str:
    """Which register to fetch: the configured **origin**, the credential's path.

    A conformant verifier follows `statusListCredential` wherever it points.
    Doing that unconditionally makes an outbound fetch to a host named inside
    the token — the same class of mistake the issuer pin at the top of
    `verify_user_vc_jwt` exists to prevent, which is why that comparison happens
    *before* anything is resolved. So configuration says which host may answer
    and the credential says which register and which index, and the two are
    reconciled here rather than trusted separately.

    This costs a correct deployment nothing: `Settings.public_base_url` in the
    identity-registry is the single source of both the `statusListCredential`
    inside the credential and the `credential_status_url` in the provisioning
    bundle.
    """
    named = entry.get("statusListCredential")
    if not isinstance(named, str) or not named:
        # Nothing to reconcile. The configured register is the only one this
        # deployment knows about, and its purpose is checked by the caller.
        return configured
    if _origin(named) != _origin(configured):
        raise HTTPException(
            401, "User VC names a credential status register on an unexpected host"
        )
    return named


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.netloc.lower()


def _published_purpose(document: dict[str, Any]) -> str:
    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        return ""
    return str(subject.get("statusPurpose") or "")


def _status_bit(document: dict[str, Any], index: int) -> bool:
    """The bit at *index* of the register's `encodedList`.

    Multibase base64url (`u` header, Bitstring Status List) or plain base64
    (StatusList2021), told apart by the header exactly as EDC's
    `BitString.Parser` does — a GZIP stream in plain base64 always starts
    `H4sI`, so the two cannot be confused. GZIP per both
    specifications, with the zlib fallback the identity-registry's
    `status_list.decode_bitstring` documents: lists published before that
    encoding was fixed are already referenced by issued credentials, and
    refusing them would revoke everyone at once.
    """
    subject = document.get("credentialSubject")
    encoded = subject.get("encodedList") if isinstance(subject, dict) else None
    if not isinstance(encoded, str) or not encoded:
        raise HTTPException(503, "Credential status register publishes no encodedList")
    try:
        if encoded.startswith("u"):
            body = encoded[1:]
            compressed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        else:
            compressed = base64.b64decode(encoded)
        try:
            bitstring = gzip.decompress(compressed)
        except (OSError, EOFError):
            bitstring = zlib.decompress(compressed)
    except Exception as exc:
        raise HTTPException(
            503, "Credential status register could not be decoded"
        ) from exc

    byte_index = index // 8
    if byte_index >= len(bitstring):
        # The credential claims a bit the register does not publish, so nothing
        # here can show it is *un*set. Fail closed, as everywhere else in this
        # module: a register that cannot answer is not a register saying yes.
        raise HTTPException(401, "User VC status index is outside its register")
    return bool(bitstring[byte_index] & (1 << (7 - (index % 8))))


def _fetch_status_list(
    url: str,
    cache: dict[str, dict[str, Any]],
    *,
    issuer: str | None = None,
    verify_signature: bool = True,
    resolver: DidWebResolver | None = None,
    ttl_seconds: float | None = None,
) -> dict[str, Any]:
    """The register at *url*, **verified** as the issuer's signed VC-JWT.

    The register is what decides whether a revoked credential is accepted, so an
    unsigned one is a register anyone on the path can rewrite: clear a bit and
    the credential is valid again. The identity-registry signs it with the trust
    anchor's key (`P-8b`), and this reads that form — `Accept:
    application/vc+jwt`, the JWT branch of `GET /status/{id}` — and verifies it
    against the key the issuer's DID document publishes, exactly as the user
    credential itself was verified. It used to ask for the unsigned JSON branch
    and trust it.

    Verified registers are cached for ``ttl_seconds`` (default
    :data:`DEFAULT_STATUS_CACHE_SECONDS`), never beyond the register's own
    ``exp``. Failures are never cached: a register that could not be read is
    asked again on the next request rather than refusing everyone for the TTL.
    """
    if url in cache:
        return cache[url]
    now = time.monotonic()
    with _STATUS_LOCK:
        hit = _STATUS_CACHE.get(url)
    if hit is not None and hit[0] > now:
        cache[url] = hit[1]
        return hit[1]

    try:
        req = Request(url, headers={"Accept": "application/vc+jwt"})
        with urlopen(req, timeout=5) as response:
            body = response.read().decode().strip()
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise HTTPException(503, "Credential status registry is not available") from exc

    document, register_exp = _verified_register(
        body, issuer=issuer, verify_signature=verify_signature, resolver=resolver
    )

    ttl = DEFAULT_STATUS_CACHE_SECONDS if ttl_seconds is None else ttl_seconds
    if ttl > 0:
        # Never past the register's own expiry: a cached register outliving the
        # signature that vouched for it would be an unsigned one by then.
        lifetime = min(ttl, max(0.0, register_exp - time.time()))
        with _STATUS_LOCK:
            _STATUS_CACHE[url] = (time.monotonic() + lifetime, document)
    cache[url] = document
    return document


def _verified_register(
    body: str,
    *,
    issuer: str | None,
    verify_signature: bool,
    resolver: DidWebResolver | None,
) -> tuple[dict[str, Any], float]:
    """The register credential inside a signed VC-JWT, and the JWT's ``exp``.

    Every failure is a **503**: the credential being checked is not at fault,
    the register is — and a register that cannot be trusted is not one saying
    "not revoked".
    """
    parts = body.split(".")
    if len(parts) != 3:
        # An unsigned JSON register is exactly what this refuses.
        raise HTTPException(
            503, "Credential status registry served no signed credential"
        )
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception as exc:
        raise HTTPException(
            503, "Credential status registry served an unreadable credential"
        ) from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise HTTPException(
            503, "Credential status registry served an unreadable credential"
        )

    register_issuer = str(payload.get("iss") or "")
    # The register must be the user credential's own issuer's — the trust
    # anchor's. A register signed by somebody else answers for nobody here.
    if issuer and register_issuer != issuer:
        raise HTTPException(503, "Credential status register is not the issuer's")

    if verify_signature:
        if header.get("alg") != "ES256":
            raise HTTPException(
                503, "Credential status register uses an unsupported algorithm"
            )
        if resolver is None:
            raise HTTPException(503, "Credential status register cannot be verified")
        try:
            document = resolver.resolve(register_issuer)
            public_key = public_key_from_jwk(assertion_jwk(document, header.get("kid")))
        except DidResolutionError as exc:
            log.error("cannot verify credential status register: %s", exc)
            raise HTTPException(
                503,
                f"Credential status register issuer could not be established: {exc}",
            ) from exc
        if not _es256_verifies(parts, public_key):
            raise HTTPException(503, "Credential status register signature is invalid")
    else:
        log.warning(
            "Reading a credential status register WITHOUT verifying its signature "
            "(VC_INSECURE_DEV=true). Local development only."
        )

    now = time.time()
    try:
        register_exp = float(payload["exp"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, "Credential status register has no expiry") from None
    if register_exp <= now:
        raise HTTPException(503, "Credential status register has expired")
    nbf = payload.get("nbf")
    if nbf is not None and float(nbf) > now + 60:
        raise HTTPException(503, "Credential status register is not valid yet")

    credential = payload.get("vc")
    if not isinstance(credential, dict):
        raise HTTPException(503, "Credential status registry served no credential")
    types = credential.get("type")
    types = [types] if isinstance(types, str) else (types or [])
    if not _STATUS_LIST_TYPES.intersection(t for t in types if isinstance(t, str)):
        raise HTTPException(503, "Credential status registry served no status list")
    if credential.get("issuer") and credential.get("issuer") != register_issuer:
        raise HTTPException(503, "Credential status register issuer claim mismatch")
    return credential, register_exp


def _read_status_list(credential_status_path: str | None) -> dict[str, Any]:
    if not credential_status_path:
        raise HTTPException(503, "Credential status registry is not configured")
    path = Path(credential_status_path)
    if not path.exists():
        raise HTTPException(503, "Credential status list is not available")
    try:
        document = json.loads(path.read_text())
    except Exception as exc:
        raise HTTPException(503, "Credential status list is invalid") from exc
    if not isinstance(document, dict):
        raise HTTPException(503, "Credential status list is invalid")
    return document
