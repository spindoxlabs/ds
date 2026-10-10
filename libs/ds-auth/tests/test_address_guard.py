"""One address guard for every did:web fetch (ADR-0029, extended to ds_auth).

The connector and provenance resolve the issuer of a person's credential through
`ds_auth.did_web`. It dialled whatever the DID's host resolved to. Now the same
rules as the identity registry's resolver, from one implementation
(`ds_auth.address_guard`): public addresses only under production; private and
loopback too under `DS_ENV=dev`; link-local (metadata), multicast, reserved and
unspecified never; every resolved address checked, at connect time; and the same
optional allowance of the dataspace's own host suffixes and private networks.

*Red:* dial a private address outside dev, check only the first answer, check a
lookup other than the one dialled, or admit a host outside the allowance.
"""

from __future__ import annotations

import httpcore
import pytest

from ds_auth import address_guard
from ds_auth.address_guard import AddressRefused, InternalAllowance, admitted_address
from ds_auth.did_web import DidResolutionError, DidWebResolver

NOT_PUBLIC = [
    "10.0.0.5",
    "172.16.3.4",
    "192.168.1.1",
    "127.0.0.1",
    "100.64.0.1",
    "::1",
    "fd00::1",
    "::ffff:10.0.0.5",
]
NEVER = ["169.254.169.254", "fe80::1", "0.0.0.0", "224.0.0.1", "240.0.0.1"]
ALLOW = InternalAllowance.parse(".ds.example.org", "10.96.0.0/12,fd00:10::/64")


# ── The rules ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("address", NOT_PUBLIC + NEVER)
def test_a_non_public_address_is_refused_outside_dev(address):
    with pytest.raises(AddressRefused):
        admitted_address("host.example.org", [address], dev=False)


@pytest.mark.parametrize("address", NEVER)
def test_link_local_and_unroutable_addresses_are_refused_even_in_dev(address):
    with pytest.raises(AddressRefused, match="link-local, multicast, reserved"):
        admitted_address("host.example.org", [address], dev=True)


@pytest.mark.parametrize("address", ["10.0.0.5", "172.18.0.7", "127.0.0.1", "::1"])
def test_dev_admits_the_local_topology(address):
    assert admitted_address("rec.dataspaces.localhost", [address], dev=True)


def test_a_public_address_is_admitted():
    assert admitted_address("host.example.org", ["93.184.216.34"], dev=False) == (
        "93.184.216.34"
    )


def test_one_private_answer_among_public_ones_is_refused():
    with pytest.raises(AddressRefused):
        admitted_address("host.example.org", ["93.184.216.34", "10.0.0.5"], dev=False)


def test_no_address_is_refused():
    with pytest.raises(AddressRefused, match="no address"):
        admitted_address("host.example.org", [], dev=True)


# ── The allowance ────────────────────────────────────────────────────────────


def test_a_dataspace_host_may_resolve_into_a_listed_network():
    assert (
        admitted_address(
            "trust-anchor.ds.example.org", ["10.96.0.10"], dev=False, allowance=ALLOW
        )
        == "10.96.0.10"
    )


@pytest.mark.parametrize(
    "host",
    [
        "attacker.example.net",
        "ds.example.org.attacker.net",
        "evilds.example.org",
        "ds.example.org",
    ],
)
def test_a_host_outside_the_suffixes_is_refused(host):
    with pytest.raises(AddressRefused, match="non-public"):
        admitted_address(host, ["10.96.0.10"], dev=False, allowance=ALLOW)


def test_a_private_address_outside_the_listed_networks_is_refused():
    with pytest.raises(AddressRefused, match="non-public"):
        admitted_address(
            "a.ds.example.org", ["192.168.1.5"], dev=False, allowance=ALLOW
        )


@pytest.mark.parametrize("address", NEVER)
def test_the_allowance_never_admits_link_local_or_unroutable(address):
    with pytest.raises(AddressRefused):
        admitted_address("a.ds.example.org", [address], dev=False, allowance=ALLOW)


@pytest.mark.parametrize(
    ("hosts", "networks"),
    [
        (".ds.example.org", ""),  # half
        ("", "10.0.0.0/8"),  # half
        (".org", "10.0.0.0/8"),  # one label: a whole TLD
        ("*.example.org", "10.0.0.0/8"),
        (".ds.example.org", "0.0.0.0/0"),
        (".ds.example.org", "::/0"),
        (".ds.example.org", "8.8.8.0/24"),  # public
        (".ds.example.org", "169.254.0.0/16"),  # link-local
        (".ds.example.org", "127.0.0.0/8"),  # loopback
        (".ds.example.org", "not-a-network"),
    ],
)
def test_an_unsound_allowance_is_refused_at_parse(hosts, networks):
    with pytest.raises(ValueError):
        InternalAllowance.parse(hosts, networks)


def test_the_empty_allowance_is_falsy_and_a_single_host_is_a_32():
    assert not InternalAllowance.parse("", "")
    one = InternalAllowance.parse("ds.example.org", "192.168.1.10/32")
    assert one and one.admits(
        "a.ds.example.org", __import__("ipaddress").ip_address("192.168.1.10")
    )


# ── At connect time, in the resolver the connector and provenance use ───────


class _Stop(Exception):
    pass


@pytest.fixture
def network(monkeypatch):
    """Scripted DNS, and a dialler that records the address and stops."""
    answers: dict[str, list[str]] = {}
    dialled: list[str] = []

    def lookup(host, port):
        return answers[host]

    def connect_tcp(self, host, port, **kwargs):
        dialled.append(host)
        raise httpcore.ConnectError("stop here")

    monkeypatch.setattr(address_guard, "_lookup_sync", lookup)
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", connect_tcp)
    return answers, dialled


def test_the_resolver_refuses_a_private_issuer_host_outside_dev(network):
    answers, dialled = network
    answers["anchor.ds.example.org"] = ["10.96.0.10"]
    resolver = DidWebResolver(dev=False)
    with pytest.raises(DidResolutionError, match="non-public"):
        resolver.resolve("did:web:anchor.ds.example.org")
    assert dialled == []


def test_the_resolver_dials_exactly_the_checked_address(network):
    answers, dialled = network
    answers["anchor.example.org"] = ["93.184.216.34"]
    with pytest.raises(DidResolutionError):
        DidWebResolver(dev=False).resolve("did:web:anchor.example.org")
    assert dialled == ["93.184.216.34"]


def test_the_resolver_admits_the_allowance(network):
    answers, dialled = network
    answers["anchor.ds.example.org"] = ["10.96.0.10"]
    with pytest.raises(DidResolutionError):
        DidWebResolver(dev=False, allowance=ALLOW).resolve(
            "did:web:anchor.ds.example.org"
        )
    assert dialled == ["10.96.0.10"]


def test_the_resolver_admits_the_local_topology_in_dev(network):
    answers, dialled = network
    answers["anchor.dataspaces.localhost"] = ["127.0.0.1"]
    with pytest.raises(DidResolutionError):
        DidWebResolver(dev=True).resolve("did:web:anchor.dataspaces.localhost")
    assert dialled == ["127.0.0.1"]


def test_the_resolver_never_dials_metadata_even_in_dev(network):
    answers, dialled = network
    answers["anchor.dataspaces.localhost"] = ["169.254.169.254"]
    with pytest.raises(DidResolutionError, match="link-local"):
        DidWebResolver(dev=True, allowance=ALLOW).resolve(
            "did:web:anchor.dataspaces.localhost"
        )
    assert dialled == []


def test_the_posture_defaults_to_ds_env(network, monkeypatch):
    answers, dialled = network
    answers["anchor.ds.example.org"] = ["10.96.0.10"]
    monkeypatch.setenv("DS_ENV", "production")
    with pytest.raises(DidResolutionError, match="non-public"):
        DidWebResolver().resolve("did:web:anchor.ds.example.org")
    monkeypatch.setenv("DS_ENV", "dev")
    with pytest.raises(DidResolutionError):
        DidWebResolver().resolve("did:web:anchor.ds.example.org")
    assert dialled == ["10.96.0.10"]


def test_the_shared_resolver_takes_the_service_allowance(monkeypatch):
    from ds_auth import user_credentials

    user_credentials.reset_resolver()
    try:
        resolver = user_credentials.get_resolver(allowance=ALLOW)
        assert resolver.allowance == ALLOW
    finally:
        user_credentials.reset_resolver()


def test_verify_user_vc_jwt_takes_the_allowance():
    import inspect

    from ds_auth.user_credentials import verify_user_vc_jwt

    assert "did_web_allowance" in inspect.signature(verify_user_vc_jwt).parameters
