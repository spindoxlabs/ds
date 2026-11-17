"""The ingress controller switch and instance isolation, over the pilot render.

Plan `the-charts-speak-traefik`. `global.ingress.controller: traefik` renders
IngressRoute + Middleware + Certificate and no Ingress. The nginx default renders
what it always did. The cross-namespace NetworkPolicies admit this instance's
participant namespaces by name. Every test names the change that turns it red.
"""

from __future__ import annotations

import pytest
from conftest import find

REC, DSO = "example-rec", "example-dso"
AUTHORITY = "example-ds"
NS = {REC: f"example-ds-{REC}", DSO: f"example-ds-{DSO}"}
ANCHOR_HOST = "trust-anchor.ds.example.org"
PORTAL_HOST = "portal.ds.example.org"
TRAEFIK_KINDS = {"IngressRoute", "Middleware", "Certificate"}

# The headers the portal builds a session from, and the ones a proxy in front of
# it may emit: a client must never be able to supply any of them.
IDENTITY_HEADERS = {
    "X-Auth-Request-Access-Token",
    "X-Auth-Request-Email",
    "X-Auth-Request-User",
    "X-Auth-Request-Preferred-Username",
    "X-Auth-Request-Groups",
    "X-Forwarded-User",
    "X-Forwarded-Email",
    "X-Forwarded-Preferred-Username",
}


def _traefik(values: dict) -> None:
    ing = values["global"].setdefault("ingress", {})
    ing["controller"] = "traefik"
    ing["controllerNamespace"] = "example-ingress"
    ing["controllerPodLabels"] = {"app.kubernetes.io/name": "traefik"}
    ing["traefik"] = {"ingressClass": "traefik"}


@pytest.fixture(scope="module")
def traefik(render_pilot) -> list[dict]:
    return render_pilot(values=_traefik).ok()


def _kinds(objects: list[dict]) -> set[str]:
    return {o["kind"] for o in objects}


def _route(objects, name, namespace) -> dict:
    return find(objects, "IngressRoute", name, namespace)


def _middleware(objects, name, namespace) -> dict:
    return find(objects, "Middleware", name, namespace)


# ── The switch ────────────────────────────────────────────────────────────────


def test_nginx_is_the_default_and_renders_no_traefik_object(pilot):
    """*Red:* default `global.ingress.controller` to traefik, or render a
    traefik template without the mode check."""
    kinds = _kinds(pilot)
    assert "Ingress" in kinds
    assert not kinds & TRAEFIK_KINDS, kinds & TRAEFIK_KINDS


def test_traefik_mode_renders_no_ingress(traefik):
    """An Ingress beside the routes would be served by a Traefik that reads
    plain Ingress, with its nginx annotations ignored: the portal open, did:web
    on the wrong path. *Red:* drop the mode check from an `ingress.yaml`."""
    assert not [o for o in traefik if o["kind"] == "Ingress"]
    assert {"IngressRoute", "Middleware", "Certificate"} <= _kinds(traefik)


def test_an_unknown_controller_fails_the_render(render_pilot):
    """*Red:* fall back to a mode instead of failing in `ds.ingress.controller`."""

    def bad(v: dict) -> None:
        v["global"].setdefault("ingress", {})["controller"] = "haproxy"

    r = render_pilot(values=bad)
    assert r.returncode != 0
    assert "global.ingress.controller" in r.stderr, r.stderr[-2000:]


def test_every_traefik_object_carries_the_ingress_class(traefik):
    """GKE-style Traefik filters CRDs on `kubernetes.io/ingress.class`. *Red:*
    drop `ds.traefik.metadataAnnotations` from a template."""
    for o in traefik:
        if o["kind"] in {"IngressRoute", "Middleware"}:
            ann = o["metadata"].get("annotations") or {}
            assert ann.get("kubernetes.io/ingress.class") == "traefik", o["metadata"]


def test_without_an_ingress_class_no_annotation_is_set(render_pilot):
    """*Red:* default the class instead of leaving it unset."""

    def no_class(v: dict) -> None:
        _traefik(v)
        v["global"]["ingress"]["traefik"] = {}

    objects = render_pilot(values=no_class).ok()
    for o in objects:
        if o["kind"] in {"IngressRoute", "Middleware"}:
            assert "kubernetes.io/ingress.class" not in (
                o["metadata"].get("annotations") or {}
            )


# ── did:web and DSP ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("p", [REC, DSO])
def test_the_participant_did_document_is_rewritten_to_its_registry(traefik, p):
    """The participant host is its did:web identity. *Red:* drop the
    middleware from the did route, or point it at another path."""
    host = f"{p}.ds.example.org"
    route = _route(traefik, f"ds-edc-{p}", NS[p])
    did = [r for r in route["spec"]["routes"] if "/.well-known/did.json" in r["match"]]
    assert len(did) == 1
    assert did[0]["match"] == f"Host(`{host}`) && Path(`/.well-known/did.json`)"
    assert did[0]["services"] == [{"name": f"ds-identity-registry-{p}", "port": 30005}]
    (mw,) = did[0]["middlewares"]
    replaced = _middleware(traefik, mw["name"], NS[p])["spec"]["replacePath"]["path"]
    assert replaced == f"/dids/did:web:{host}/did.json"


@pytest.mark.parametrize("p", [REC, DSO])
def test_dspace_version_is_rewritten_under_the_protocol_context(traefik, p):
    """*Red:* drop the replacePath from the dspace-version route."""
    route = _route(traefik, f"ds-edc-{p}", NS[p])
    (r,) = [x for x in route["spec"]["routes"] if "dspace-version" in x["match"]]
    (mw,) = r["middlewares"]
    path = _middleware(traefik, mw["name"], NS[p])["spec"]["replacePath"]["path"]
    assert path == "/protocol/.well-known/dspace-version"


@pytest.mark.parametrize("p", [REC, DSO])
def test_management_and_control_are_routed_nowhere(traefik, p):
    """Same denial as nginx mode. *Red:* route the EDC Service on any port but
    protocol."""
    route = _route(traefik, f"ds-edc-{p}", NS[p])
    edc_ports = {
        s["port"]
        for r in route["spec"]["routes"]
        for s in r["services"]
        if s["name"] == f"ds-edc-{p}"
    }
    protocol = find(traefik, "Service", f"ds-edc-{p}", NS[p])
    named = {x["name"]: x["port"] for x in protocol["spec"]["ports"]}
    assert edc_ports == {named["protocol"]}, edc_ports


def test_the_anchor_did_document_is_rewritten(traefik):
    """*Red:* drop the anchor's did middleware."""
    route = _route(traefik, "ds-identity-registry", AUTHORITY)
    (did,) = [r for r in route["spec"]["routes"] if "did.json" in r["match"]]
    (mw,) = did["middlewares"]
    path = _middleware(traefik, mw["name"], AUTHORITY)["spec"]["replacePath"]["path"]
    assert path == f"/dids/did:web:{ANCHOR_HOST}/did.json"
    matches = " ".join(r["match"] for r in route["spec"]["routes"])
    for public in ("/status", "/trust", "/issuer"):
        assert f"`{public}`" in matches, public
    for private in ("/admin", "/owners", "/memberships", "/onboarding", "/metrics"):
        assert private not in matches, private


def test_a_prefix_matches_by_path_element(traefik):
    """An Ingress `Prefix` matches `/status/...`, not `/statusx`. *Red:* render a
    bare PathPrefix(`/status`)."""
    route = _route(traefik, "ds-identity-registry", AUTHORITY)
    matches = " ".join(r["match"] for r in route["spec"]["routes"])
    assert "PathPrefix(`/status/`)" in matches
    assert "PathPrefix(`/status`)" not in matches


# ── TLS ───────────────────────────────────────────────────────────────────────


def test_one_certificate_per_host(traefik):
    """cert-manager does not read IngressRoutes, so each host gets exactly one
    Certificate from the chart that owns it. *Red:* render a Certificate in
    ds-oauth2-proxy, or none in ds-edc."""
    hosts = [
        name
        for o in traefik
        if o["kind"] == "Certificate"
        for name in o["spec"]["dnsNames"]
    ]
    assert sorted(hosts) == sorted(
        [ANCHOR_HOST, PORTAL_HOST, f"{REC}.ds.example.org", f"{DSO}.ds.example.org"]
    )
    for o in traefik:
        if o["kind"] == "Certificate":
            assert o["spec"]["issuerRef"] == {
                "group": "cert-manager.io",
                "kind": "ClusterIssuer",
                "name": "example-issuer",
            }


def test_every_route_on_a_host_serves_that_hosts_certificate(traefik):
    """A route without `tls` is not served on websecure; one with another
    secret serves the wrong certificate. *Red:* drop the tls block from the
    oauth2-proxy route."""
    certs = {
        o["spec"]["dnsNames"][0]: o["spec"]["secretName"]
        for o in traefik
        if o["kind"] == "Certificate"
    }
    for o in traefik:
        if o["kind"] != "IngressRoute":
            continue
        host = o["spec"]["routes"][0]["match"].split("`")[1]
        assert o["spec"]["tls"]["secretName"] == certs[host], o["metadata"]["name"]


def test_a_provided_secret_renders_no_certificate(render_pilot):
    """*Red:* render the Certificate when `tls.secretName` is set."""

    def provided(v: dict) -> None:
        _traefik(v)
        v["global"]["ingress"]["tls"] = {"secretName": "operator-cert"}

    objects = render_pilot(values=provided).ok()
    assert not [o for o in objects if o["kind"] == "Certificate"]
    for o in objects:
        if o["kind"] == "IngressRoute":
            assert o["spec"]["tls"] == {"secretName": "operator-cert"}


# ── The portal: strip first, then forwardAuth ─────────────────────────────────


def test_the_portal_routes_first_middleware_strips_the_identity_headers(traefik):
    """**Security-critical.** The portal builds its session from
    `X-Auth-Request-Access-Token` without verifying it. Traefik's forwardAuth
    does not touch a header it is not told about, so the strip must run before
    anything else, on the walled route and on the carve-outs alike, and must
    delete every identity header. *Red:* move the strip after forwardAuth, drop
    it from the public route, or remove a header from `stripHeaders`."""
    ns = NS[REC]
    for name in (f"ds-portal-{REC}", f"ds-portal-{REC}-public"):
        for r in _route(traefik, name, ns)["spec"]["routes"]:
            first = r["middlewares"][0]["name"]
            headers = _middleware(traefik, first, ns)["spec"]["headers"]
            stripped = {
                k for k, v in headers["customRequestHeaders"].items() if v == ""
            }
            missing = IDENTITY_HEADERS - stripped
            assert not missing, f"{name}: {missing} reach the portal from the client"


def test_the_walled_route_authenticates_through_the_proxy(traefik):
    """*Red:* drop the forwardAuth from the walled route, aim it at another
    namespace (multi-tenant admission refuses that), or trust client
    X-Forwarded-* headers."""
    ns = NS[REC]
    (r,) = _route(traefik, f"ds-portal-{REC}", ns)["spec"]["routes"]
    assert r["match"] == f"Host(`{PORTAL_HOST}`) && PathPrefix(`/`)"
    names = [m["name"] for m in r["middlewares"]]
    assert names == [f"ds-portal-{REC}-strip-identity", f"ds-portal-{REC}-auth"]
    fa = _middleware(traefik, names[1], ns)["spec"]["forwardAuth"]
    assert fa["address"] == f"http://ds-oauth2-proxy-{REC}.{ns}.svc.cluster.local:4180/"
    assert fa["trustForwardHeader"] is False
    # Listed → deleted from the request and set from the proxy's answer only.
    assert {"X-Auth-Request-Access-Token", "Authorization"} <= set(
        fa["authResponseHeaders"]
    )


def test_the_public_carve_outs_skip_only_the_forward_auth(traefik):
    """*Red:* add the forwardAuth to the public route (an applicant with no
    account could never reach /join), or match a bare prefix."""
    ns = NS[REC]
    (r,) = _route(traefik, f"ds-portal-{REC}-public", ns)["spec"]["routes"]
    assert [m["name"] for m in r["middlewares"]] == [f"ds-portal-{REC}-strip-identity"]
    assert "PathPrefix(`/join/`)" in r["match"]
    assert "PathPrefix(`/_app/immutable/`)" in r["match"]
    assert "`/_app/`" not in r["match"]


def test_the_oauth2_route_is_plain(traefik):
    """A user reaches /oauth2 precisely without a session. *Red:* add the
    portal's chain to it."""
    (r,) = _route(traefik, f"ds-oauth2-proxy-{REC}", NS[REC])["spec"]["routes"]
    assert "middlewares" not in r
    assert "PathPrefix(`/oauth2/`)" in r["match"]


def test_traefik_mode_uses_no_middleware_a_tenant_platform_refuses(traefik):
    """Multi-tenant Traefik platforms refuse `errors`, `plugin`, `buffering` and
    `ipWhiteList` in tenant namespaces at admission. *Red:* render one."""
    refused = {"errors", "plugin", "buffering", "ipWhiteList"}
    for o in traefik:
        if o["kind"] == "Middleware":
            assert not refused & set(o["spec"]), o["metadata"]["name"]


# ── NetworkPolicy ─────────────────────────────────────────────────────────────


def _from_ingress(objects, release, ns):
    pol = find(objects, "NetworkPolicy", f"{release}-from-ingress", ns)
    (rule,) = pol["spec"]["ingress"]
    (peer,) = rule["from"]
    return peer


def test_the_controller_namespace_and_pods_are_the_only_ingress_peer(traefik):
    """*Red:* drop `controllerPodLabels` from `ds.networkPolicy.fromIngressController`."""
    for release, ns in (
        (f"ds-edc-{REC}", NS[REC]),
        (f"ds-portal-{REC}", NS[REC]),
        (f"ds-oauth2-proxy-{REC}", NS[REC]),
        ("ds-identity-registry", AUTHORITY),
    ):
        peer = _from_ingress(traefik, release, ns)
        assert peer["namespaceSelector"]["matchLabels"] == {
            "kubernetes.io/metadata.name": "example-ingress"
        }
        assert peer["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "traefik"}


def test_without_pod_labels_the_whole_controller_namespace_is_the_peer(pilot):
    """The previous behaviour stays the default. *Red:* require the labels."""
    peer = _from_ingress(pilot, f"ds-edc-{REC}", NS[REC])
    assert "podSelector" not in peer


def _peer_namespaces(policy: dict) -> list[str]:
    (rule,) = policy["spec"]["ingress"]
    (peer,) = rule["from"]
    (expr,) = peer["namespaceSelector"]["matchExpressions"]
    assert expr["key"] == "kubernetes.io/metadata.name" and expr["operator"] == "In"
    return expr["values"]


def test_cross_namespace_peers_are_this_instances_namespaces_by_name(pilot):
    """Two data spaces on one cluster must not admit each other, and a namespace
    must not admit itself by carrying a label. *Red:* select by the participant
    label again, or omit a participant from the computed list."""
    expected = sorted(NS.values())
    anchor = find(pilot, "NetworkPolicy", "ds-identity-registry-from-participants", AUTHORITY)
    assert sorted(_peer_namespaces(anchor)) == expected
    for p in (REC, DSO):
        edc = find(pilot, "NetworkPolicy", f"ds-edc-{p}-dsp-from-peers", NS[p])
        assert sorted(_peer_namespaces(edc)) == expected
    for o in pilot:
        if o["kind"] == "NetworkPolicy":
            assert "dataspace.spindoxlabs.io/participant" not in str(o["spec"]), o[
                "metadata"
            ]["name"]


def test_a_disabled_participant_is_not_admitted(render_pilot):
    """*Red:* compute the list from `.Values.participants` instead of the enabled ones."""

    def off(v: dict) -> None:
        next(p for p in v["participants"] if p["name"] == DSO)["enabled"] = False

    objects = render_pilot(values=off).ok()
    anchor = find(objects, "NetworkPolicy", "ds-identity-registry-from-participants", AUTHORITY)
    assert _peer_namespaces(anchor) == [NS[REC]]


# ── The namespaces release ────────────────────────────────────────────────────


def test_pre_created_namespaces_skip_the_release_and_its_needs(render_pilot):
    """A platform that owns the Namespace objects. *Red:* render ds-namespaces,
    or leave a `needs` on it, with `create: false`."""

    def precreated(v: dict) -> None:
        v["global"]["namespaces"]["create"] = False

    r = render_pilot(values=precreated)
    objects = r.ok()
    assert not [o for o in objects if o["kind"] == "Namespace"]
    assert "ds-namespaces" not in r.stderr


def test_the_namespaces_release_lives_where_it_is_told(render_pilot):
    """*Red:* hard-code `default` again."""

    def elsewhere(v: dict) -> None:
        v["global"]["namespaces"]["releaseNamespace"] = "example-system"

    r = render_pilot(values=elsewhere)
    assert [o for o in r.ok() if o["kind"] == "Namespace"]
    assert r.namespaces["ds-namespaces"] == "example-system"
    # The `needs` follow it: helmfile refuses a need on a release it does not have.


def test_create_must_be_a_boolean(render_pilot):
    """*Red:* accept a string."""

    def bad(v: dict) -> None:
        v["global"]["namespaces"]["create"] = "no"

    r = render_pilot(values=bad)
    assert r.returncode != 0
    assert "global.namespaces.create" in r.stderr, r.stderr[-2000:]
