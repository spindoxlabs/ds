"""The dataspace's own hosts may resolve to a private address, and nothing else may.

Under `DS_ENV=production` the outbound transport (did:web documents, credential
delivery) dials only globally routable addresses. A cluster whose DNS answers the
dataspace's own hosts with a private address (a split-horizon resolver, an in-cluster
proxy) then refuses every enrolment. ADR-0029: an explicit allowance, a list of host
suffixes **and** the networks they may resolve to, both required, empty by default.

*Red:* admit a private address for any host, or drop the network check, or accept a
suffix or network that admits everything.
"""

from __future__ import annotations

import pytest

from identity_registry.config import Settings
from identity_registry.services.did_resolver import (
    DidResolutionError,
    InternalAllowance,
    admitted_address,
)

ALLOW = InternalAllowance.parse(".ds.example.org", "10.96.0.0/12,fd00:10::/64")


# ── What the allowance admits ──────────────────────────────────────────────


def test_a_dataspace_host_may_resolve_into_a_listed_network():
    assert (
        admitted_address(
            "trust-anchor.ds.example.org", ["10.96.0.10"], dev=False, allowance=ALLOW
        )
        == "10.96.0.10"
    )
    assert (
        admitted_address(
            "holder.ds.example.org", ["fd00:10::5"], dev=False, allowance=ALLOW
        )
        == "fd00:10::5"
    )


def test_without_the_allowance_the_same_answer_is_refused():
    with pytest.raises(DidResolutionError, match="non-public"):
        admitted_address("trust-anchor.ds.example.org", ["10.96.0.10"], dev=False)


@pytest.mark.parametrize(
    "host",
    [
        "attacker.example.net",  # any other host
        "ds.example.org.attacker.net",  # the suffix in the middle
        "evilds.example.org",  # a label that merely ends with the suffix text
        "ds.example.org",  # the apex itself is not under the suffix
    ],
)
def test_a_host_outside_the_suffixes_is_refused_as_today(host):
    with pytest.raises(DidResolutionError, match="non-public"):
        admitted_address(host, ["10.96.0.10"], dev=False, allowance=ALLOW)


def test_a_private_address_outside_the_listed_networks_is_refused():
    with pytest.raises(DidResolutionError, match="non-public"):
        admitted_address(
            "holder.ds.example.org", ["192.168.1.5"], dev=False, allowance=ALLOW
        )


@pytest.mark.parametrize(
    "address", ["169.254.169.254", "fe80::1", "224.0.0.1", "0.0.0.0", "240.0.0.1"]
)
def test_link_local_metadata_multicast_reserved_and_unspecified_stay_refused(address):
    with pytest.raises(
        DidResolutionError, match="link-local, multicast, reserved or unspecified"
    ):
        admitted_address("holder.ds.example.org", [address], dev=False, allowance=ALLOW)


def test_every_address_must_be_admissible_not_just_the_first():
    with pytest.raises(DidResolutionError):
        admitted_address(
            "holder.ds.example.org",
            ["10.96.0.10", "192.168.1.5"],
            dev=False,
            allowance=ALLOW,
        )


def test_a_trailing_dot_and_case_do_not_matter():
    assert admitted_address(
        "Holder.DS.Example.org.", ["10.96.0.10"], dev=False, allowance=ALLOW
    )


def test_the_empty_allowance_changes_nothing():
    empty = InternalAllowance.parse("", "")
    assert not empty
    with pytest.raises(DidResolutionError, match="non-public"):
        admitted_address(
            "holder.ds.example.org", ["10.96.0.10"], dev=False, allowance=empty
        )


# ── What is refused at start ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hosts", "networks", "why"),
    [
        (".ds.example.org", "", "both"),
        ("", "10.0.0.0/8", "both"),
        (".", "10.0.0.0/8", "suffix"),
        (".org", "10.0.0.0/8", "suffix"),
        ("org", "10.0.0.0/8", "suffix"),
        ("*.ds.example.org", "10.0.0.0/8", "suffix"),
        (".ds..example.org", "10.0.0.0/8", "suffix"),
        (".ds.example.org", "0.0.0.0/0", "network"),
        (".ds.example.org", "::/0", "network"),
        (".ds.example.org", "169.254.0.0/16", "network"),
        (".ds.example.org", "224.0.0.0/4", "network"),
        (".ds.example.org", "127.0.0.0/8", "network"),
        (
            ".ds.example.org",
            "8.8.8.0/24",
            "network",
        ),  # public: never needed, never allowed
        (".ds.example.org", "not-a-network", "network"),
    ],
)
def test_an_allowance_that_admits_too_much_or_is_malformed_is_refused(
    hosts, networks, why
):
    with pytest.raises(ValueError, match=why):
        InternalAllowance.parse(hosts, networks)


def test_the_settings_refuse_a_half_configured_allowance():
    with pytest.raises(ValueError, match="both"):
        Settings(_env_file=None, did_web_internal_hosts=".ds.example.org")


def test_the_settings_carry_a_valid_allowance():
    s = Settings(
        _env_file=None,
        did_web_internal_hosts="ds.example.org",  # a leading dot is implied
        did_web_internal_networks="10.96.0.0/12",
    )
    allowance = InternalAllowance.from_settings(s)
    assert allowance.suffixes == (".ds.example.org",)
    assert admitted_address(
        "a.ds.example.org", ["10.96.0.1"], dev=False, allowance=allowance
    )


# ── One host address: the shape of a cluster whose pods reach the ingress through ──
# ── the node itself (no hairpin to the public address) ─────────────────────────────

HOST_ONLY = InternalAllowance.parse(".ds.example.org", "192.168.1.10/32")


def test_a_single_host_address_is_an_allowance():
    assert (
        admitted_address(
            "holder.ds.example.org", ["192.168.1.10"], dev=False, allowance=HOST_ONLY
        )
        == "192.168.1.10"
    )


def test_the_neighbouring_address_is_refused():
    with pytest.raises(DidResolutionError, match="non-public"):
        admitted_address(
            "holder.ds.example.org", ["192.168.1.11"], dev=False, allowance=HOST_ONLY
        )
