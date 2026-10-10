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
