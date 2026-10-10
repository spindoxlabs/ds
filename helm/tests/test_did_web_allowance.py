"""The did:web internal allowance (ADR-0029) reaches every identity registry, or none.

`authority.identityRegistry.didWeb.{internalHosts,internalNetworks}` is the
dataspace's own: the anchor resolves the participants' hosts at enrolment and the
participants resolve theirs, so the helmfile forwards the one block to every registry
release. Default empty: no variable rendered, the resolver unchanged. Half of it fails
the render, as it fails the service at load.

*Red:* forward it to the anchor only, render one variable without the other, or render
an empty variable by default.
"""

from __future__ import annotations

from collections.abc import Callable

from conftest import PilotRender, container_env, find

HOSTS = "IDENTITY_REGISTRY_DID_WEB_INTERNAL_HOSTS"
NETS = "IDENTITY_REGISTRY_DID_WEB_INTERNAL_NETWORKS"
REGISTRIES = {
    "ds-identity-registry": "example-ds",
    "ds-identity-registry-example-rec": "example-ds-example-rec",
    "ds-identity-registry-example-dso": "example-ds-example-dso",
}


def _with(hosts, networks):
    def mutate(values: dict) -> None:
        values["authority"]["identityRegistry"]["didWeb"] = {
            "internalHosts": hosts,
            "internalNetworks": networks,
        }

    return mutate


def _env(objects, release, ns):
    return container_env(find(objects, "Deployment", release, ns))


def test_by_default_no_registry_carries_the_allowance(render_pilot: Callable[..., PilotRender]):
    objects = render_pilot().ok()
    for release, ns in REGISTRIES.items():
        env = _env(objects, release, ns)
        assert HOSTS not in env and NETS not in env, release


def test_the_allowance_reaches_every_registry(render_pilot: Callable[..., PilotRender]):
    objects = render_pilot(values=_with([".ds.example.org"], ["192.168.1.10/32"])).ok()
    for release, ns in REGISTRIES.items():
        env = _env(objects, release, ns)
        assert env.get(HOSTS) == ".ds.example.org", release
        assert env.get(NETS) == "192.168.1.10/32", release


def test_half_an_allowance_does_not_render(render_pilot: Callable[..., PilotRender]):
    for hosts, nets in (([".ds.example.org"], []), ([], ["192.168.1.10/32"])):
        result = render_pilot(values=_with(hosts, nets))
        assert result.returncode != 0
        assert "didWeb" in result.stderr


# ── The connectors and provenance (ADR-0029, extended to ds_auth) ───────────
#
# They resolve the issuer of a person's credential through `ds_auth.did_web`, now
# behind the same address guard. The dataspace's one block reaches them too, as
# each service's own variables; a participant's block may set its own.

SERVICES = {
    "ds-connector-example-rec": ("example-ds-example-rec", "CONNECTOR"),
    "ds-connector-example-dso": ("example-ds-example-dso", "CONNECTOR"),
    "ds-provenance-example-rec": ("example-ds-example-rec", "PROVENANCE"),
    "ds-provenance-example-dso": ("example-ds-example-dso", "PROVENANCE"),
}


def test_by_default_no_connector_or_provenance_carries_it(render_pilot):
    objects = render_pilot().ok()
    for release, (ns, prefix) in SERVICES.items():
        env = _env(objects, release, ns)
        assert f"{prefix}_DID_WEB_INTERNAL_HOSTS" not in env, release
        assert f"{prefix}_DID_WEB_INTERNAL_NETWORKS" not in env, release


def test_the_dataspace_block_reaches_every_connector_and_provenance(render_pilot):
    objects = render_pilot(values=_with([".ds.example.org"], ["192.168.1.10/32"])).ok()
    for release, (ns, prefix) in SERVICES.items():
        env = _env(objects, release, ns)
        assert env.get(f"{prefix}_DID_WEB_INTERNAL_HOSTS") == ".ds.example.org", release
        assert env.get(f"{prefix}_DID_WEB_INTERNAL_NETWORKS") == "192.168.1.10/32", (
            release
        )


def test_a_participant_block_sets_its_own(render_pilot):
    def mutate(values: dict) -> None:
        _with([".ds.example.org"], ["192.168.1.10/32"])(values)
        rec = next(p for p in values["participants"] if p["name"] == "example-rec")
        rec.setdefault("connector", {})["didWeb"] = {
            "internalHosts": [".ds.example.org"],
            "internalNetworks": ["10.96.0.0/12"],
        }

    objects = render_pilot(values=mutate).ok()
    rec = _env(objects, "ds-connector-example-rec", "example-ds-example-rec")
    dso = _env(objects, "ds-connector-example-dso", "example-ds-example-dso")
    assert rec["CONNECTOR_DID_WEB_INTERNAL_NETWORKS"] == "10.96.0.0/12"
    assert dso["CONNECTOR_DID_WEB_INTERNAL_NETWORKS"] == "192.168.1.10/32"


def test_half_an_allowance_does_not_render_for_a_connector_or_provenance(render_pilot):
    for block in ("connector", "provenance"):

        def mutate(values: dict, block=block) -> None:
            rec = next(p for p in values["participants"] if p["name"] == "example-rec")
            rec.setdefault(block, {})["didWeb"] = {
                "internalHosts": [".ds.example.org"],
                "internalNetworks": [],
            }

        result = render_pilot(values=mutate)
        assert result.returncode != 0, block
        assert "didWeb" in result.stderr, block


# ── The EDC (ADR-0029: `DidWebGuardExtension`) ───────────────────────────────
#
# The EDC resolves the counterparty's did:web during DCP; ds's extension guards it
# and reads `ds.did.web.internal.{hosts,networks}` from its properties.

EDCS = {
    "ds-edc-example-rec": "example-ds-example-rec",
    "ds-edc-example-dso": "example-ds-example-dso",
}


def _edc_properties(objects, release, ns) -> str:
    return find(objects, "ConfigMap", release, ns)["data"]["edc.properties"]


def test_by_default_no_edc_carries_it(render_pilot):
    objects = render_pilot().ok()
    for release, ns in EDCS.items():
        assert "ds.did.web.internal" not in _edc_properties(objects, release, ns), release


def test_the_dataspace_block_reaches_every_edc(render_pilot):
    objects = render_pilot(values=_with([".ds.example.org"], ["192.168.1.10/32"])).ok()
    for release, ns in EDCS.items():
        props = _edc_properties(objects, release, ns)
        assert "ds.did.web.internal.hosts=.ds.example.org" in props, release
        assert "ds.did.web.internal.networks=192.168.1.10/32" in props, release


def test_half_an_allowance_does_not_render_for_an_edc(render_pilot):
    def mutate(values: dict) -> None:
        rec = next(p for p in values["participants"] if p["name"] == "example-rec")
        rec.setdefault("edc", {})["didWeb"] = {
            "internalHosts": [],
            "internalNetworks": ["192.168.1.10/32"],
        }

    result = render_pilot(values=mutate)
    assert result.returncode != 0
    assert "didWeb" in result.stderr
