"""`E2E-03` — the api-contract sweep derives its route table from the services.

The row asked for six missing connector routes to be added to a literal table.
Measured across the four apps the table claimed to cover, it was **70 of 110**
guarded routes, and four of the six were the *item* under a collection already
probed — so a longer table was the wrong fix. These tests pin the derivation
that replaced it, and the three things that derivation cannot see on its own:

* the security-scheme name is a second copy of a string `ds_auth` owns;
* a route declared `include_in_schema=False` is absent from the document and so
  absent from the sweep — no service may declare one;
* a route in neither classification table must fail the sweep rather than be
  quietly skipped.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows.api_contract import (
    ANONYMOUS_ROUTES,
    PUBLIC_ROUTES,
    REFUSAL_STATUSES,
    SELF_AUTHENTICATED_ROUTES,
    SWEPT_SERVICES,
    ApiContractFlow,
)
from ds_e2e.models import FlowResult
from ds_e2e.route_inventory import (
    PATH_PARAM,
    PERMISSION_SCHEME,
    Route,
    routes_from_openapi,
    routes_held_by,
    token_scopes,
)

REPO = Path(__file__).resolve().parents[3]

SERVICE_SOURCES = {
    "connector": REPO / "services/connector/src/connector",
    "identity-registry": REPO / "services/identity-registry/src/identity_registry",
    "provenance": REPO / "services/provenance/src/provenance",
    "federated-catalog": REPO / "services/federated-catalog/src/federated_catalog",
}


def spec(*operations: tuple[str, str, list[str] | None]) -> dict:
    """A minimal OpenAPI document carrying just what the sweep reads."""
    paths: dict[str, dict] = {}
    for path, method, permissions in operations:
        operation: dict = {"responses": {}}
        if permissions is not None:
            operation["security"] = [{PERMISSION_SCHEME: permissions}]
        paths.setdefault(path, {})[method.lower()] = operation
    return {"openapi": "3.1.0", "paths": paths}


# ── reading the document ─────────────────────────────────────────────────────

def test_a_route_is_guarded_because_the_app_says_so():
    routes = routes_from_openapi(
        "connector",
        spec(
            ("/provider/assets", "get", ["connector.provider.read", "connector.admin"]),
            ("/health", "get", None),
        ),
    )
    guarded = {r.template: r for r in routes if r.guarded}
    assert set(guarded) == {"/provider/assets"}
    assert guarded["/provider/assets"].permissions == (
        "connector.provider.read",
        "connector.admin",
    )
    assert [r for r in routes if not r.guarded][0].template == "/health"


def test_a_security_requirement_for_another_scheme_is_not_a_ds_guard():
    """Only `ds_auth`'s scheme means "a permission is required here".

    A service adding its own scheme — an API key on an operator endpoint, say —
    must not read as permission-guarded, or the wrong-scope battery would probe
    it with a bearer token and pass on a refusal that means something else.
    """
    document = spec(("/thing", "get", None))
    document["paths"]["/thing"]["get"]["security"] = [{"ApiKeyAuth": []}]
    assert routes_from_openapi("connector", document)[0].guarded is False


def test_non_operation_keys_are_not_probed_as_methods():
    """OpenAPI allows `parameters` and `summary` beside the verbs."""
    document = spec(("/thing", "get", None))
    document["paths"]["/thing"]["parameters"] = [{"name": "x", "in": "query"}]
    document["paths"]["/thing"]["summary"] = "a thing"
    assert [r.method for r in routes_from_openapi("connector", document)] == ["GET"]


def test_a_path_parameter_becomes_a_value_that_resolves_to_nothing():
    route = Route("identity-registry", "DELETE", "/admin/memberships/{did}/{org}")
    assert route.path == "/admin/memberships/e2e-nonexistent/e2e-nonexistent"


@pytest.mark.parametrize("service", sorted(SERVICE_SOURCES))
def test_the_substituted_value_is_no_services_literal_segment(service: str):
    """`/admin/participants/{did}` must not probe `/admin/participants/check`.

    A path parameter is filled with a sentinel, and a sentinel that happened to
    be a literal segment of a sibling route would send the probe to a different
    route with a different guard — reporting on something it never asked about.
    """
    for path in SERVICE_SOURCES[service].rglob("*.py"):
        assert PATH_PARAM not in path.read_text(), f"{path} uses the probe sentinel"


# ── the token, read from the realm rather than from a comment ────────────────

def _token(claims: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(claims).encode())
    payload = raw.rstrip(b"=").decode()
    return f"header.{payload}.signature"


def test_the_held_routes_come_from_the_tokens_own_scope_claim():
    routes = [
        Route(
            "federated-catalog", "GET", "/catalog", ("catalog.read", "catalog.admin")
        ),
        Route("connector", "POST", "/provider/sync", ("connector.provider.write",)),
    ]
    scopes = token_scopes(_token({"scope": "openid profile catalog.read"}))
    assert [r.template for r in routes_held_by(routes, scopes)] == ["/catalog"]


def test_an_unreadable_token_excuses_no_route():
    """The safe direction: over-probe rather than skip.

    A token the harness cannot parse must not turn into "this client holds
    everything", which would empty the wrong-scope battery while it reported a
    pass.
    """
    assert token_scopes("not-a-jwt") == frozenset()
    assert token_scopes(_token({"no_scope_claim": True})) == frozenset()
    routes = [Route("connector", "GET", "/x", ("connector.admin",))]
    assert routes_held_by(routes, token_scopes("not-a-jwt")) == []


# ── the classification tables ────────────────────────────────────────────────

def test_a_route_cannot_be_both_open_and_self_authenticated():
    """Opposite expectations: one must answer 200, the other must refuse.

    The old pair of tables carried the same rule for public-versus-guarded; it
    survives the rewrite because the two remaining hand-kept tables can still
    disagree with each other.
    """
    assert not (set(ANONYMOUS_ROUTES) & set(SELF_AUTHENTICATED_ROUTES))


def test_every_pinned_public_probe_is_a_route_declared_anonymous():
    """`PUBLIC_ROUTES` asserts 200; `ANONYMOUS_ROUTES` decides who may.

    A 200 probe on a route the classification does not call anonymous would be
    asserted open by one table and swept for refusal by the other.
    """
    declared = {(svc, method, path) for svc, method, path in ANONYMOUS_ROUTES}
    for service, method, path in PUBLIC_ROUTES:
        if service == "dataset-api":
            continue  # not a ds service; only its health is probed
        assert (service, method, path) in declared, f"{service} {method} {path}"


def test_a_refusal_must_be_the_guards():
    """422 is 4xx and is not a refusal, which is how a probe passes vacuously."""
    assert 422 not in REFUSAL_STATUSES
    assert set(REFUSAL_STATUSES) == {401, 403}


# ── the two holes the derivation cannot see ──────────────────────────────────

def test_the_scheme_name_agrees_with_ds_auth():
    """One string, two holders — checked, because `ds-e2e` does not import `ds_auth`.

    A path dependency would rebuild this package on every auth change for one
    constant (`E2E-10` removed exactly such a dependency). The copy is safe only
    while something compares them, and a silent disagreement would empty the
    guarded set: every route would read as unguarded, the wrong-scope battery
    would probe nothing, and the inventory step would report 110 unclassified
    routes rather than a pass.
    """
    source = (REPO / "libs/ds-auth/src/ds_auth/fastapi.py").read_text()
    match = re.search(r'PERMISSION_SCHEME_NAME\s*=\s*"([^"]+)"', source)
    assert match, "ds_auth.fastapi no longer defines PERMISSION_SCHEME_NAME"
    assert match.group(1) == PERMISSION_SCHEME


@pytest.mark.parametrize("service", sorted(SERVICE_SOURCES))
def test_no_service_hides_a_route_from_its_openapi_document(service: str):
    """`include_in_schema=False` removes a route from the sweep's only source.

    That is the one weakness of deriving from OpenAPI rather than from the route
    table itself, so the fix is to have nothing to derive around: no route is
    hidden, and this test is what keeps it that way.

    It used to be a weaker rule — hide what you like, but declare each one in
    `HIDDEN_ROUTES` — and `POST /consent/register-transfer` was the single
    entry. The declaration bought nothing. **This is an open-source project and
    the route table is public**, so hiding a route conceals it from readers of
    the document and from nobody else, while turning a documentation decision
    into a security-sweep decision and adding a second place to forget. The
    route is published now and the list is gone.

    `GET /metrics` does not appear here: it is installed by `ds_obs` rather than
    declared in a service, so it is outside `SERVICE_SOURCES` by construction.
    """
    hidden: set[str] = set()
    for path in SERVICE_SOURCES[service].rglob("*.py"):
        source = path.read_text()
        for match in re.finditer(
            r'@\w+\.(get|post|put|patch|delete)\(\s*"([^"]*)"[^)]*include_in_schema\s*=\s*False',
            source,
            re.S,
        ):
            hidden.add(match.group(2))
    assert not hidden, (
        f"{service} hides {sorted(hidden)} from its OpenAPI document, so the "
        "api-contract sweep cannot see them. Publish the route: the sweep derives "
        "from the document, and the source is public either way."
    )


# ── the inventory step ───────────────────────────────────────────────────────

class FakeHttp:
    """Answers `/openapi.json` from a dict keyed by the URL the flow builds.

    A `KeyError` here means the step asked for something the test did not
    stage — which is worth failing on rather than answering with a default.
    """

    def __init__(self, documents: dict[str, dict]):
        self.documents = documents

    def raw(self, method: str, url: str, **kwargs) -> tuple[int, dict]:
        return 200, self.documents[url]


def _flow(documents_by_service: dict[str, dict]) -> ApiContractFlow:
    settings = E2ESettings(_env_file=None)
    flow = ApiContractFlow(settings, http=None)
    by_url = {
        flow._url(service, "/openapi.json"): document
        for service, document in documents_by_service.items()
    }
    flow.http = FakeHttp(by_url)
    return flow


def _documents(**per_service: dict) -> dict[str, dict]:
    return {service: per_service.get(service, spec()) for service in SWEPT_SERVICES}


def test_an_unclassified_route_fails_the_sweep():
    """The property the whole rewrite exists for.

    A route that is neither guarded nor declared open is the state the old table
    was in for 40 routes, and it produced a green run. It now fails, and names
    the route.
    """
    flow = _flow(_documents(provenance=spec(("/prov/new-thing", "get", None))))
    result = FlowResult(flow_name="t")
    assert flow._check_route_inventory(result) is False
    step = result.steps[-1]
    assert "provenance GET /prov/new-thing" in str(step.data)


def test_a_declaration_for_a_route_that_no_longer_exists_fails():
    """An exemption outliving the thing it exempted is how the table drifted."""
    flow = _flow(_documents())
    result = FlowResult(flow_name="t")
    assert flow._check_route_inventory(result) is False
    assert "stale_declarations" in str(result.steps[-1].data)


def test_a_route_declared_open_but_guarded_by_the_app_fails():
    """The app wins, loudly.

    A declaration that a guarded route is open would exclude it from the
    wrong-scope battery — the weaker claim quietly deciding the stronger one.
    """
    guarded_health = spec(("/health", "get", ["connector.admin"]))
    flow = _flow({s: spec() for s in SWEPT_SERVICES} | {"connector": guarded_health})
    result = FlowResult(flow_name="t")
    assert flow._check_route_inventory(result) is False
    assert "declared_open_but_guarded" in str(result.steps[-1].data)


def test_the_two_roles_of_the_connector_share_one_classification():
    """`connector` and `consumer-connector` are one image started twice.

    Keyed by endpoint, every shared router would need two entries and the pair
    would drift; keyed by app, `/consent/my` is declared once and covers both.
    """
    flow = ApiContractFlow(E2ESettings(_env_file=None), http=None)
    consumer_side = Route("consumer-connector", "GET", "/consent/my")
    assert flow._key(consumer_side) == ("connector", "GET", "/consent/my")
    assert flow._is_anonymous(Route("consumer-connector", "GET", "/health"))
