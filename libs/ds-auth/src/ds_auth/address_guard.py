"""Which addresses an outbound fetch to a counterparty-chosen host may reach.

ADR-0029 (scope extended to every did:web fetch). The host in a did:web identifier
is chosen by whoever presents the DID, so the address it resolves to is checked
**at connect time** — on the address actually dialled, not on a separate lookup a
second DNS answer could contradict — and only a public address is admitted. Under
`DS_ENV=dev` (and only there) private and loopback addresses are admitted too,
because the local topology resolves `*.localhost` and compose service names to
exactly those. Link-local (which includes cloud metadata), multicast, reserved and
unspecified addresses are refused in every posture. **Every** resolved address
must pass, not just the first.

One implementation for the two resolvers that fetch did:web documents: the
identity registry's (async, `identity_registry.services.did_resolver`, which wraps
these rules in its own httpx transport) and `ds_auth.did_web` (sync, the issuer of
a person's credential, used by the connector and provenance), through
:func:`guarded_sync_transport`.

The optional :class:`InternalAllowance` admits the dataspace's own hosts into the
private networks a deployment names (split-horizon DNS, an in-cluster proxy).
Each service configures its own (`<PREFIX>_DID_WEB_INTERNAL_HOSTS` /
`_NETWORKS`), validated here, at load.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpcore
import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class AddressRefused(Exception):
    """A host resolved to an address this fetch may not dial."""


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
    networks: tuple[IPNetwork, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.suffixes)

    @classmethod
    def parse(cls, hosts: str, networks: str) -> InternalAllowance:
        host_items = [
            h.strip().lower().rstrip(".") for h in (hosts or "").split(",") if h.strip()
        ]
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
                raise ValueError(
                    f"did:web internal allowance: {n!r} is not a network"
                ) from exc
            link_local = ipaddress.ip_network(
                "169.254.0.0/16" if net.version == 4 else "fe80::/10"
            )
            if (
                net.prefixlen == 0
                or not net.is_private
                or net.is_link_local
                or net.is_loopback
                or net.is_multicast
                or net.is_unspecified
                or net.overlaps(link_local)  # type: ignore[arg-type]
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
        """From a service's `did_web_internal_hosts` / `did_web_internal_networks`."""
        return cls.parse(
            getattr(settings, "did_web_internal_hosts", "") or "",
            getattr(settings, "did_web_internal_networks", "") or "",
        )

    def admits(self, host: str, ip: IPAddress) -> bool:
        name = host.lower().rstrip(".")
        return any(name.endswith(s) for s in self.suffixes) and any(
            ip in n for n in self.networks
        )

    def describe(self) -> str:
        return (
            f"hosts under {', '.join(self.suffixes)} may resolve to "
            f"{', '.join(str(n) for n in self.networks)}"
        )


def address_refusal(
    ip: IPAddress,
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
        reason = address_refusal(ip, dev=dev, host=host, allowance=allowance)
        if reason:
            raise AddressRefused(f"{host} resolves to {reason} ({ip})")
        chosen = chosen or str(ip)
    if chosen is None:
        raise AddressRefused(f"{host} resolves to no address")
    return chosen


def _lookup_sync(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class GuardedSyncBackend(httpcore.NetworkBackend):
    """Resolves the host itself, checks every answer, and dials the admitted one.

    TLS still names the original host — httpcore takes the SNI and certificate
    hostname from the request, not from what was connected to.
    """

    def __init__(
        self, *, dev: bool, allowance: InternalAllowance | None = None
    ) -> None:
        self._dev = dev
        self._allowance = allowance
        self._inner = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        try:
            addresses = _lookup_sync(host, port)
        except OSError as exc:
            raise httpcore.ConnectError(f"cannot resolve {host}: {exc}") from exc
        try:
            address = admitted_address(
                host, addresses, dev=self._dev, allowance=self._allowance
            )
        except AddressRefused as exc:
            raise httpcore.ConnectError(str(exc)) from exc
        return self._inner.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(self, *args: Any, **kwargs: Any) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("unix sockets are not reachable from here")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


def guarded_sync_transport(
    *,
    dev: bool,
    allowance: InternalAllowance | None = None,
    ssl_context: ssl.SSLContext | None = None,
) -> httpx.BaseTransport:
    """An httpx transport that dials only admissible addresses.

    Pair it with ``follow_redirects=False`` and ``trust_env=False`` on the client:
    a redirect or an environment proxy would each move the request somewhere this
    check never saw (a proxy is the address dialled, not the target).

    ``ssl_context`` defaults to the platform's (`ssl.create_default_context()`,
    which honours `SSL_CERT_FILE`), the trust ``urllib`` used before this guard.
    """
    context = ssl_context or ssl.create_default_context()
    transport = httpx.HTTPTransport(verify=context, trust_env=False, retries=0)
    # httpx builds its pool with the default network backend and offers no
    # argument for another one, so the pool is rebuilt with the same TLS context
    # and this backend (the identity registry's async transport does the same).
    transport._pool = httpcore.ConnectionPool(
        ssl_context=context,
        network_backend=GuardedSyncBackend(dev=dev, allowance=allowance),
        retries=0,
    )
    return transport
