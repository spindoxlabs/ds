"""did:web resolution for services that verify somebody else's signature.

`DID-17`. This exists because the connector and ds-provenance verified a data
subject's credential against the trust anchor's public key **read from a mounted
file** (`CONNECTOR_TRUST_ANCHOR_KEY_PATH`). That is the `P-8a` class — *never
against a key this deployment happens to hold* — and its practical consequence
was that rotating the anchor's key meant redeploying every service that mounts
it, in lockstep, or accepting silent verification failures until they caught up.

The document is the authority. A key read from anywhere else is a second copy of
a fact that already has one home, and a second copy is a thing that can be stale.

## Two questions, and this module answers only the first

**"Is this signature really from the key that DID publishes?"** — resolution,
here. **"Is that DID somebody this dataspace accredited, and for what?"** — the
dataspace trust list (`DSSC-TRF-05`, `-07`, `-17`), also here in `trust_list`,
because a resolvable key proves authorship and says nothing about authority. A
verifier that asks only the first accepts a perfectly valid credential from an
issuer nobody accredited.

## Why this is cached and the identity-registry's resolver is not

`identity_registry.services.did_resolver` deliberately has no cache: it resolves
once per negotiation. This one runs on **every request carrying `X-User-VC`**, so
an uncached resolver would put a synchronous outbound fetch in front of every
call. The TTL is the rotation window — the interval during which this service may
still verify against a key the issuer has replaced — so it is short, and it is a
setting rather than a constant.

Sync on purpose: `verify_user_vc_jwt` is sync and called from sync dependency
functions in two services. An async variant would fork the call graph for no gain.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePublicNumbers,
)

log = logging.getLogger(__name__)

DID_WEB_PREFIX = "did:web:"
WELL_KNOWN_PATH = ".well-known/did.json"

#: How long a resolved document may be reused. Also the worst-case window in
#: which this service still accepts a key the issuer has rotated away from.
DEFAULT_TTL_SECONDS = 300.0


class DidResolutionError(Exception):
    """A DID could not be resolved, or its document carries no usable key."""


def did_web_url(did: str, *, use_https: bool = True) -> str:
    """Map a ``did:web`` identifier to the URL its document is served from.

    ``did:web:example.com``        → ``https://example.com/.well-known/did.json``
    ``did:web:example.com:a:b``    → ``https://example.com/a/b/did.json``
    ``did:web:example.com%3A3000`` → ``https://example.com:3000/.well-known/did.json``

    The same three rules as `identity_registry.services.did_resolver.did_web_url`.
    Duplicated rather than shared because this library must not depend on a
    service; if they ever disagree the e2e `dcp-trust` flow fails, since it
    resolves the same documents these services do.
    """
    if not did.startswith(DID_WEB_PREFIX):
        raise DidResolutionError(f"Only did:web is supported, got: {did}")
    identifier = did[len(DID_WEB_PREFIX) :]
    if not identifier:
        raise DidResolutionError("did:web with no identifier")

    segments = [unquote(segment) for segment in identifier.split(":")]
    host = segments[0]
    if not host:
        raise DidResolutionError(f"did:web with no host: {did}")

    scheme = "https" if use_https else "http"
    if len(segments) == 1:
        return f"{scheme}://{host}/{WELL_KNOWN_PATH}"
    return f"{scheme}://{host}/{'/'.join(segments[1:])}/did.json"


def _b64url_decode(value: str) -> bytes:
    padding = 4 - len(value) % 4
    return base64.urlsafe_b64decode(value + "=" * (padding % 4))


def public_key_from_jwk(jwk: dict[str, Any]):
    """An EC P-256 public key from a JWK, or a refusal.

    Curve and key type are checked rather than assumed: an issuer that published
    an RSA or P-384 key would otherwise have its coordinates read as if they were
    P-256, and the verification that followed would be meaningless rather than
    wrong.
    """
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise DidResolutionError(
            f"unsupported key type {jwk.get('kty')}/{jwk.get('crv')} — "
            "user credentials are ES256 over P-256"
        )
    try:
        x = int.from_bytes(_b64url_decode(jwk["x"]), "big")
        y = int.from_bytes(_b64url_decode(jwk["y"]), "big")
    except (KeyError, ValueError, TypeError) as exc:
        raise DidResolutionError(
            "verification key is not a well-formed EC JWK"
        ) from exc
    return EllipticCurvePublicNumbers(x=x, y=y, curve=SECP256R1()).public_key()


def assertion_jwk(document: dict[str, Any], kid: str | None) -> dict[str, Any]:
    """The JWK a *credential's* signature must be checked against.

    With a ``kid`` the matching ``verificationMethod`` is used; without one, the
    document must name exactly one ``assertionMethod`` — the relationship W3C VC
    defines for issuing, as opposed to ``authentication`` (logging in) or
    ``capabilityInvocation`` (the relationship DCP's self-issued tokens use).

    Ambiguity is a refusal, never a guess: picking "the first key" would make a
    document with two of them verify against whichever was serialised first.
    """
    methods = document.get("verificationMethod") or []
    if not isinstance(methods, list) or not methods:
        raise DidResolutionError("DID document has no verificationMethod")

    if kid:
        for method in methods:
            if isinstance(method, dict) and method.get("id") == kid:
                jwk = method.get("publicKeyJwk")
                if not isinstance(jwk, dict):
                    raise DidResolutionError(
                        f"verificationMethod {kid} carries no publicKeyJwk"
                    )
                return jwk
        raise DidResolutionError(f"no verificationMethod matches kid {kid}")

    assertion = document.get("assertionMethod") or []
    candidates = [
        m for m in methods if isinstance(m, dict) and m.get("id") in assertion
    ]
    if len(candidates) != 1:
        raise DidResolutionError(
            "credential carries no kid and the DID document does not name "
            "exactly one assertionMethod"
        )
    jwk = candidates[0].get("publicKeyJwk")
    if not isinstance(jwk, dict):
        raise DidResolutionError("assertionMethod carries no publicKeyJwk")
    return jwk


@dataclass
class _Entry:
    value: dict[str, Any]
    expires_at: float


class DidWebResolver:
    """Resolves did:web documents over HTTP, with a TTL cache.

    One instance per process. Thread-safe because the services using it serve
    requests from a thread pool for sync endpoints, and two threads racing on a
    cache miss would otherwise both fetch — harmless, but the lock is one line.

    **Only the document's own `id` is trusted to identify it.** A host that
    returns somebody else's document is a resolution failure, not a key.
    """

    def __init__(
        self,
        *,
        use_https: bool = True,
        timeout_seconds: float = 5.0,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._use_https = use_https
        self._timeout = timeout_seconds
        self._ttl = ttl_seconds
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def resolve(self, did: str) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(did)
            if cached is not None and cached.expires_at > now:
                return cached.value

        document = self._fetch(did)
        with self._lock:
            self._cache[did] = _Entry(document, time.monotonic() + self._ttl)
        return document

    def invalidate(self, did: str | None = None) -> None:
        """Drop one document, or all of them. For key rotation and for tests."""
        with self._lock:
            if did is None:
                self._cache.clear()
            else:
                self._cache.pop(did, None)

    def _fetch(self, did: str) -> dict[str, Any]:
        url = did_web_url(did, use_https=self._use_https)
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                document = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise DidResolutionError(f"{did} is unreachable at {url}: {exc}") from exc

        if not isinstance(document, dict):
            raise DidResolutionError(f"{did} did not return a DID document at {url}")
        if document.get("id") != did:
            raise DidResolutionError(
                f"{url} served a document for {document.get('id')!r}, not {did!r}"
            )
        return document

    # ── the dataspace trust list ─────────────────────────────────────────────

    def accredited(
        self,
        trust_list_url: str,
        did: str,
        *,
        credential_type: str | None = None,
    ) -> None:
        """Refuse unless *did* is an **active** entry on the dataspace's list.

        `DSSC-TRF-05`, `-07`, `-17`, `-19`. Resolution proves who signed;
        this proves the dataspace stands behind them. Without it, a verifier
        that has been handed an issuer DID accepts everything that DID signs
        forever — including after its accreditation is withdrawn, which is the
        one event the list exists to publish.

        Revoked entries stay listed by design, so "present" is not the test:
        `status` is. And where the entry names a scope of attestation, a
        credential type outside it is refused — an accreditation to attest one
        thing is not an accreditation to attest everything.
        """
        listing = self._trust_list(trust_list_url)
        entry = next(
            (
                e
                for e in listing.get("issuers") or []
                if isinstance(e, dict) and e.get("id") == did
            ),
            None,
        )
        if entry is None:
            raise DidResolutionError(
                f"{did} is not on the dataspace trust list at {trust_list_url}"
            )
        if entry.get("status") != "active":
            raise DidResolutionError(
                f"{did} is listed with status {entry.get('status')!r} — "
                f"{entry.get('revocationReason') or 'not active'}"
            )
        scope = entry.get("scopeOfAttestation") or []
        if credential_type and scope and credential_type not in scope:
            raise DidResolutionError(
                f"{did} is not accredited to attest {credential_type} "
                f"(scope: {', '.join(scope)})"
            )

    def _trust_list(self, url: str) -> dict[str, Any]:
        """Cached exactly like a DID document, and for the same reason."""
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(url)
            if cached is not None and cached.expires_at > now:
                return cached.value
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                listing = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            # Fails **closed**: an unreachable trust list means this service
            # cannot tell an accredited issuer from a stranger, and answering
            # anyway is answering without the check.
            raise DidResolutionError(
                f"trust list at {url} is unavailable: {exc}"
            ) from exc
        if not isinstance(listing, dict):
            raise DidResolutionError(f"trust list at {url} is not a JSON object")
        with self._lock:
            self._cache[url] = _Entry(listing, time.monotonic() + self._ttl)
        return listing
