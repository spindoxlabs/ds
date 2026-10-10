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

import asyncio
import ipaddress
import json
import logging
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import anyio
import httpcore
import httpx
from ds_auth.production import is_production

log = logging.getLogger(__name__)

DID_WEB_PREFIX = "did:web:"
WELL_KNOWN_PATH = ".well-known/did.json"

#: The largest DID document this resolver reads. A document is a handful of
#: verification methods and service entries — a few kilobytes — so anything
#: approaching this is not a DID document, and reading it is memory spent on
#: somebody else's behalf.
MAX_DOCUMENT_BYTES = 256 * 1024


class DidResolutionError(Exception):
    """A DID could not be resolved, or its document carries no usable key."""


# ── Which addresses an outbound fetch may reach ─────────────────────────────
#
# The host in a did:web identifier is chosen by whoever presents the DID, and on
# the public routes that is anyone. So the address it resolves to is checked
# **at connect time** — on the address actually dialled, not on a separate
# lookup that a second DNS answer could contradict — and only a public address
# is admitted. Under `DS_ENV=dev` (and only there) private and loopback addresses
# are admitted too, because the local topology resolves `*.localhost` and compose
# service names to exactly those. Link-local (which includes cloud metadata),
# multicast, reserved and unspecified addresses are refused in every posture.


#: A host suffix: a leading dot, then at least two DNS labels (`.ds.example.org`).
#: One label (`.org`) would admit a whole top-level domain.
_SUFFIX = re.compile(r"^(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){2,}$")


@dataclass(frozen=True)
class InternalAllowance:
    """The dataspace's own hosts, and the private networks they may resolve to.

    ADR-0029. A deployment whose cluster DNS answers its own `*.<baseDomain>` with a
    private address (split horizon, an in-cluster proxy) names those hosts' suffixes
    **and** the networks: only a host under a listed suffix, resolving into a listed
    network, gets a private address admitted. Link-local (metadata), multicast,
    reserved and unspecified addresses stay refused for every host, and every host
    outside the suffixes is treated exactly as without the allowance. Empty by
    default; a half-configured or over-broad allowance is refused at load.
    """

    suffixes: tuple[str, ...] = ()
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.suffixes)

    @classmethod
    def parse(cls, hosts: str, networks: str) -> InternalAllowance:
        host_items = [h.strip().lower().rstrip(".") for h in (hosts or "").split(",") if h.strip()]
        net_items = [n.strip() for n in (networks or "").split(",") if n.strip()]
        if not host_items and not net_items:
            return cls()
        if not host_items or not net_items:
            raise ValueError(
                "did:web internal allowance: set both the host suffixes and the "
                "networks they may resolve to, or neither"
            )
        suffixes = []
        for h in host_items:
            suffix = h if h.startswith(".") else f".{h}"
            if not _SUFFIX.match(suffix):
                raise ValueError(
                    f"did:web internal allowance: {h!r} is not a host suffix of at "
                    "least two DNS labels (e.g. .ds.example.org)"
                )
            suffixes.append(suffix)
        nets = []
        for n in net_items:
            try:
                net = ipaddress.ip_network(n, strict=False)
            except ValueError as exc:
                raise ValueError(f"did:web internal allowance: {n!r} is not a network") from exc
            if (
                net.prefixlen == 0
                or not net.is_private
                or net.is_link_local
                or net.is_loopback
                or net.is_multicast
                or net.is_unspecified
                or net.overlaps(ipaddress.ip_network("169.254.0.0/16" if net.version == 4 else "fe80::/10"))
            ):
                raise ValueError(
                    f"did:web internal allowance: network {n!r} is not a private "
                    "network this allowance may name (no default route, public, "
                    "link-local, loopback or multicast range)"
                )
            nets.append(net)
        return cls(tuple(suffixes), tuple(nets))

    @classmethod
    def from_settings(cls, settings: Any) -> InternalAllowance:
        return cls.parse(
            getattr(settings, "did_web_internal_hosts", "") or "",
            getattr(settings, "did_web_internal_networks", "") or "",
        )

    def admits(self, host: str, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        name = host.lower().rstrip(".")
        return any(name.endswith(s) for s in self.suffixes) and any(ip in n for n in self.networks)

    def describe(self) -> str:
        return (
            f"hosts under {', '.join(self.suffixes)} may resolve to "
            f"{', '.join(str(n) for n in self.networks)}"
        )


def _address_refusal(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    dev: bool,
    host: str = "",
    allowance: InternalAllowance | None = None,
) -> str | None:
    """Why *ip* may not be dialled for *host*, or ``None`` when it may."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.is_reserved and not ip.is_loopback)
    ):
        return "a link-local, multicast, reserved or unspecified address"
    if ip.is_global:
        return None
    if dev and (ip.is_private or ip.is_loopback):
        return None
    if allowance and allowance.admits(host, ip):
        return None
    return "a non-public address"


def admitted_address(
    host: str,
    addresses: Iterable[str],
    *,
    dev: bool,
    allowance: InternalAllowance | None = None,
) -> str:
    """The address to dial for *host*, given everything it resolved to.

    **Every** address must be admissible, not just the first: a name that
    resolves to one public and one private address would otherwise reach the
    private one whenever the order changes.
    """
    chosen: str | None = None
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
        reason = _address_refusal(ip, dev=dev, host=host, allowance=allowance)
        if reason:
            raise DidResolutionError(f"{host} resolves to {reason} ({ip})")
        chosen = chosen or str(ip)
    if chosen is None:
        raise DidResolutionError(f"{host} resolves to no address")
    return chosen


async def _lookup(host: str, port: int) -> list[str]:
    infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class _AdmittedAddressBackend(httpcore.AsyncNetworkBackend):
    """Resolves the host itself, checks the result, and dials that address.

    TLS still names the original host — httpcore takes the SNI and certificate
    hostname from the request, not from what was connected to.
    """

    def __init__(self, *, dev: bool, allowance: InternalAllowance | None = None) -> None:
        self._dev = dev
        self._allowance = allowance
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                addresses = await _lookup(host, port)
        except (OSError, TimeoutError) as exc:
            raise httpcore.ConnectError(f"cannot resolve {host}: {exc}") from exc
        try:
            address = admitted_address(host, addresses, dev=self._dev, allowance=self._allowance)
        except DidResolutionError as exc:
            raise httpcore.ConnectError(str(exc)) from exc
        return await self._inner.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self, *args: Any, **kwargs: Any
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not reachable from here")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def outbound_transport(
    *, dev: bool | None = None, allowance: InternalAllowance | None = None
) -> httpx.AsyncBaseTransport:
    """An httpx transport that only dials admissible addresses.

    For every request to an address a counterparty chose: DID documents here,
    and the Storage API endpoint a holder's document publishes. Pair it with
    ``follow_redirects=False`` and ``trust_env=False`` on the client — a redirect
    or an environment proxy would each move the request somewhere this check
    never saw.
    """
    if dev is None:
        dev = not is_production()
    if allowance is None:
        from ..config import get_settings

        allowance = InternalAllowance.from_settings(get_settings())
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    # httpx builds its pool with the default network backend and offers no
    # argument for another one, so the pool is rebuilt with the same TLS
    # context and this backend.
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(trust_env=False),
        network_backend=_AdmittedAddressBackend(dev=dev, allowance=allowance),
        retries=0,
    )
    return transport


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

    **Bounded on every axis a counterparty controls** (`P-8d`): only admissible
    addresses are dialled (see :func:`outbound_transport`), no redirect is
    followed, the whole fetch has one deadline, and the body is read only up to
    :data:`MAX_DOCUMENT_BYTES`. Plain HTTP is refused outside `DS_ENV=dev`, which
    is the only posture that serves did:web without TLS.
    """

    def __init__(self, *, use_https: bool = True, timeout_seconds: float = 5.0):
        self._use_https = use_https
        self._timeout = timeout_seconds

    async def resolve(self, did: str) -> dict[str, Any]:
        if not self._use_https and is_production():
            raise DidResolutionError(
                "did:web over plain HTTP is only resolved under DS_ENV=dev"
            )
        url = did_web_url(did, use_https=self._use_https)
        try:
            async with asyncio.timeout(self._timeout):
                status_code, body = await self._fetch(url)
        except TimeoutError as exc:
            raise DidResolutionError(f"{did} timed out at {url}") from exc
        except httpx.HTTPError as exc:
            raise DidResolutionError(f"{did} is unreachable at {url}: {exc}") from exc

        if status_code != 200:
            raise DidResolutionError(f"{did} resolved to HTTP {status_code} at {url}")
        try:
            document = json.loads(body)
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

    async def _fetch(self, url: str) -> tuple[int, bytes]:
        """GET *url*: the status and at most :data:`MAX_DOCUMENT_BYTES` of body."""
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
            transport=outbound_transport(),
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return response.status_code, b""
                declared = response.headers.get("content-length")
                if (
                    declared
                    and declared.isdigit()
                    and int(declared) > MAX_DOCUMENT_BYTES
                ):
                    raise DidResolutionError(
                        f"document at {url} exceeds the size limit"
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_DOCUMENT_BYTES:
                        raise DidResolutionError(
                            f"document at {url} exceeds the size limit"
                        )
                return response.status_code, bytes(body)
