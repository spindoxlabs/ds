"""did:web resolution, and verification-key selection out of a DID document.

Used by the credential service to verify the **verifier's** self-issued token.
The verifier is a counterparty — in production it is another organisation whose
keys this registry has never seen — so the only way to check its signature is to
resolve its DID document and read the key out of it.

There is deliberately **no local-key shortcut**. Resolving through HTTP even when
this instance happens to publish the DID is what keeps the dev path and the
production path the same code; a shortcut would make every local run prove
something the deployment does not do. That is the `T-1` failure shape, and this
module exists because of a defect of exactly that kind.

Resolution rules follow the DCP specification, §Validating Self-Issued ID Tokens
(`base.protocol.md`) and the did:web method.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote

import httpx

log = logging.getLogger(__name__)

DID_WEB_PREFIX = "did:web:"
WELL_KNOWN_PATH = ".well-known/did.json"


class DidResolutionError(Exception):
    """A DID could not be resolved, or its document carries no usable key."""


def did_web_url(did: str, *, use_https: bool = True) -> str:
    """Map a ``did:web`` identifier to the URL its document is served from.

    ``did:web:example.com``            → ``https://example.com/.well-known/did.json``
    ``did:web:example.com:a:b``        → ``https://example.com/a/b/did.json``
    ``did:web:example.com%3A3000``     → ``https://example.com:3000/.well-known/did.json``
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
    path = "/".join(segments[1:])
    return f"{scheme}://{host}/{path}/did.json"


def normalize_did_web(did: str) -> str:
    """Restore the percent-encoded port a URL path decoded away.

    ``did:web:host%3A8080`` is the canonical spelling — the method percent-encodes
    the port because a bare colon already means "path segment follows". A DID in a
    URL path arrives decoded, as ``did:web:host:8080``, and then matches nothing:
    every lookup, every ``client_id`` comparison and every key resolution is a
    string equality against the stored, encoded form.

    Only an all-digit second segment is treated as a port, which is what
    distinguishes ``did:web:host:8080`` from ``did:web:users.example.org:alice``.

    Portless DIDs are unaffected, which is why no deployment has hit this: it
    surfaces the moment a registry runs anywhere but :443.
    """
    if not did.startswith(DID_WEB_PREFIX):
        return did
    segments = did[len(DID_WEB_PREFIX) :].split(":")
    if len(segments) >= 2 and segments[1].isdigit():
        segments[0] = f"{segments[0]}%3A{segments[1]}"
        del segments[1]
    return DID_WEB_PREFIX + ":".join(segments)


def verification_key(document: dict[str, Any], kid: str | None) -> dict[str, Any]:
    """Select the public JWK a token's signature must be checked against.

    Follows the DCP rules verbatim:

    * with a ``kid`` header, the matching ``verificationMethod`` entry is used;
    * without one, a single entry holding the ``capabilityInvocation``
      relationship is used;
    * anything else — no match, several candidates, a method carrying no JWK —
      is a rejection, never a guess.
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
        raise DidResolutionError(f"No verificationMethod matches kid {kid}")

    invocation = document.get("capabilityInvocation") or []
    candidates = [
        method
        for method in methods
        if isinstance(method, dict) and method.get("id") in invocation
    ]
    if len(candidates) != 1:
        raise DidResolutionError(
            "Token carries no kid and the DID document does not have exactly one "
            "capabilityInvocation verification method"
        )
    jwk = candidates[0].get("publicKeyJwk")
    if not isinstance(jwk, dict):
        raise DidResolutionError("capabilityInvocation method carries no publicKeyJwk")
    return jwk


class DidResolver:
    """Fetches did:web documents over HTTP.

    Deliberately without a cache. A presentation query happens once per
    negotiation, not per request, and an unbounded resolution cache is the same
    defect class as the two `EDC-11` is about — one that also has to be
    invalidated when a participant rotates a key.
    """

    def __init__(self, *, use_https: bool = True, timeout_seconds: float = 5.0):
        self._use_https = use_https
        self._timeout = timeout_seconds

    async def resolve(self, did: str) -> dict[str, Any]:
        url = did_web_url(did, use_https=self._use_https)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise DidResolutionError(f"{did} is unreachable at {url}: {exc}") from exc

        if response.status_code != 200:
            raise DidResolutionError(
                f"{did} resolved to HTTP {response.status_code} at {url}"
            )
        try:
            document = response.json()
        except ValueError as exc:
            raise DidResolutionError(f"{did} did not return JSON at {url}") from exc

        if not isinstance(document, dict):
            raise DidResolutionError(f"{did} did not return a DID document at {url}")
        if document.get("id") != did:
            # DCP: the `sub` claim must equal the DID document `id`. A document
            # answering for a DID other than the one asked for is how a host that
            # serves several DIDs lets one impersonate another.
            raise DidResolutionError(
                f"{did} resolved to a document identifying {document.get('id')!r}"
            )
        return document
