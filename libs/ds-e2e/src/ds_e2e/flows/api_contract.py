"""API contract sweep — the guard rail under every other flow.

The functional flows prove the happy path works. This one proves the API
*refuses* correctly, which is the property that decides whether the platform is
deployable outside a lab. It asserts four things about every service:

1. **The public perimeter is exactly what we reviewed.** A pinned list of routes
   that must answer with no credential. It is a two-way assertion: these must
   not regress to 401 (they are protocol surfaces — DID resolution, StatusList,
   the ODRL vocabulary — that unauthenticated parties must read), and nothing
   else may join them silently.
2. **Every guarded route refuses an anonymous caller.** Not "most routes" — every
   route each service publishes, asserting a 401. A 200 here is an open endpoint;
   a 500 is a guard that crashed instead of denying.
3. **Authentication is not authorisation.** The same routes replayed with a real,
   fully-valid token that simply lacks the scope. Anything other than a refusal
   means the route authenticates but never checks what the caller may do.
4. **Bad input is rejected, not absorbed.** Malformed bodies, out-of-range
   paging, unknown enum values and traversal-shaped path parameters must produce
   4xx. A 500 means the input reached something that was not expecting it.

Every refusal is additionally checked for leakage: no stack traces, no driver
names, no connection strings in an error body.

**The route table is derived, not listed** (`E2E-03`). Batteries 2 and 3 used to
walk a literal table maintained beside the routers it mirrored; measured against
the apps, it covered 70 of 110 guarded routes, and four of the six missing
connector routes were the *item* under a collection that was already probed —
the signature of a list kept by hand. `ds_e2e.route_inventory` reads each
service's own `/openapi.json` instead, so the only thing left to declare is
which routes are anonymous **by design**, and an unclassified route fails the
sweep rather than escaping it.

Needs no EDC: connector, identity-registry, provenance, federated-catalog and
Keycloak are enough.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult
from ds_e2e.route_inventory import (
    Route,
    routes_from_openapi,
    routes_held_by,
    token_scopes,
)

log = logging.getLogger(__name__)

# The services whose whole published surface is swept. `dataset-api` is not one:
# the real data plane is celine's and is not a ds service (root `AGENTS.md`), so
# only its health probe appears below.
SWEPT_SERVICES = (
    "connector",
    "consumer-connector",
    "identity-registry",
    "provenance",
    "federated-catalog",
)

# Substrings that must never reach a client in an error body.
LEAK_MARKERS = (
    "Traceback",
    "psycopg",
    "sqlalchemy",
    "asyncpg",
    "postgresql://",
    "SELECT ",
    "/usr/lib/python",
    "site-packages",
)

# ── The anonymous surface: the only part still declared by hand ──────────────
#
# Batteries 2 and 3 walk what the services publish, so nothing below enumerates
# a guarded route. What is left to declare is the opposite: which routes are
# reachable, or refuse, **without** a bearer permission — and why. A published
# route in none of these tables is swept for refusal, which is the fail-safe
# direction: forgetting to classify a new route makes it probed, not exempt.
#
# Keyed by *app*, because `connector` and `consumer-connector` are one image in
# two roles and their shared routers would otherwise be listed twice.

# Named once, because the same mechanism covers a whole router and repeating the
# sentence per route is how two entries come to disagree about one guard.
SUBJECT_VC = "DataSubject VC-JWT"
CONSUMER_AUTH = "ConsumerUser VC-JWT or connector.consumer.read"
DID_WEB = "did:web resolution — an unknown verifier must resolve it"

# What a probe puts where a real caller would put an identifier. It has to be
# schema-valid and resolve to nothing: a probe that succeeded would be asserting
# on a request the platform accepted.
PROBE_ID = "e2e-nonexistent"
PROBE_ADDRESS = "http://provider.invalid/protocol/2025-1"

# Reachable with no credential by design. Widening this table widens the
# anonymous perimeter, so each entry says what an unauthenticated party is doing
# with it.
ANONYMOUS_ROUTES: dict[tuple[str, str, str], str] = {
    ("connector", "GET", "/health"): "liveness",
    ("connector", "GET", "/ns"): "the vocabulary index this participant serves",
    ("connector", "GET", "/ns/policy"): "the ODRL profile a policy engine dereferences",
    ("connector", "GET", "/ns/sharing-offers"): "the sharing-offer vocabulary",
    ("connector", "GET", "/ns/vocabularies"): "the fetched-vocabulary index",
    ("connector", "GET", "/ns/{slug}"): (
        "one fetched vocabulary. No 200 probe: it is 404 until a vocabulary has "
        "been cached, so asserting a status here would assert cache state"
    ),
    ("identity-registry", "GET", "/health"): "liveness",
    ("identity-registry", "GET", "/.well-known/did.json"): (
        f"{DID_WEB}, for a `did:web:<host>` with no path. **404 here, measured**: "
        "every dev DID carries a path, so nothing resolves the root document and "
        "there is no 200 to pin"
    ),
    ("identity-registry", "GET", "/dids/{did}/did.json"): DID_WEB,
    ("identity-registry", "GET", "/{did_path}/did.json"): DID_WEB,
    ("identity-registry", "GET", "/status/{list_id}"): (
        "StatusList revocation — a checker must read it before it has any "
        "relationship with this dataspace (rulebook P-13)"
    ),
    ("identity-registry", "GET", "/trust"): (
        "the accreditation list (DSSC-TRF-05, -07, -17), public for the same reason"
    ),
    ("identity-registry", "GET", "/issuer/metadata"): (
        "what this issuer can issue, read before a client has an identity here"
    ),
    ("provenance", "GET", "/health"): "liveness",
    ("provenance", "GET", "/prov/context"): "the PROV-O JSON-LD context",
    ("federated-catalog", "GET", "/health"): "liveness",
    ("federated-catalog", "GET", "/catalog/context"): "the DCAT JSON-LD context",
}

# The subset of the above asserted to answer **200** anonymously, as concrete
# paths. Separate from the classification because a route can be anonymous
# without having a status worth pinning: `/ns/{slug}` and `/status/{list_id}`
# answer about a resource that may not exist yet, and `/dids/{did}/did.json` is
# derived at run time from the provider DID (see `_check_public_perimeter`).
#
# `dataset-api` appears only here: the real data plane is celine's, not a ds
# service, so its surface is out of scope and its health is not.
PUBLIC_ROUTES: list[tuple[str, str, str]] = [
    ("connector", "GET", "/health"),
    ("connector", "GET", "/ns"),
    ("connector", "GET", "/ns/policy"),
    ("connector", "GET", "/ns/sharing-offers"),
    ("connector", "GET", "/ns/vocabularies"),
    ("identity-registry", "GET", "/health"),
    ("identity-registry", "GET", "/trust"),
    ("identity-registry", "GET", "/issuer/metadata"),
    ("provenance", "GET", "/health"),
    ("provenance", "GET", "/prov/context"),
    ("federated-catalog", "GET", "/health"),
    ("federated-catalog", "GET", "/catalog/context"),
    ("dataset-api", "GET", "/health"),
]

# Refuses an anonymous caller, but not through `require_permission` — so it
# carries no `DataspacePermission` requirement and the bearer-token battery
# would prove nothing about it. Each entry names the mechanism and the flow that
# exercises it positively, because a negative sweep alone cannot tell a route
# that verifies a credential from one that rejects every caller.
SELF_AUTHENTICATED_ROUTES: dict[tuple[str, str, str], str] = {
    # X-User-VC + X-Subject-Id. Asserted negatively by `_check_user_vc_surface`
    # below — including a forged signature — and positively by `consent-request`
    # and `uc2`.
    ("connector", "GET", "/consent/my"): SUBJECT_VC,
    ("connector", "GET", "/consent/my/shares"): SUBJECT_VC,
    ("connector", "POST", "/consent/my/shares"): SUBJECT_VC,
    ("connector", "GET", "/consent/my/{consent_id}"): SUBJECT_VC,
    ("connector", "POST", "/consent/my/{consent_id}/approve"): SUBJECT_VC,
    ("connector", "POST", "/consent/my/{consent_id}/reject"): SUBJECT_VC,
    ("connector", "POST", "/consent/my/{consent_id}/revoke"): SUBJECT_VC,
    ("connector", "GET", "/consent/status"): SUBJECT_VC,
    ("provenance", "GET", "/prov/my/events"): f"{SUBJECT_VC}; asserted by `lineage`",
    # `require_consumer_catalog_caller` and its siblings take **either** a
    # ConsumerUser VC-JWT or `connector.consumer.read`, and decide inside the
    # handler rather than in a dependency — so the app publishes no requirement
    # and the wrong-scope battery cannot reach them. Asserted positively by
    # `smoke`, `uc1` and `two-providers`.
    ("connector", "POST", "/consumer/catalog"): CONSUMER_AUTH,
    ("connector", "POST", "/consumer/negotiate"): CONSUMER_AUTH,
    ("connector", "POST", "/consumer/transfer"): CONSUMER_AUTH,
    ("connector", "POST", "/consumer/flow"): CONSUMER_AUTH,
    ("connector", "GET", "/consumer/requests"): CONSUMER_AUTH,
    ("connector", "POST", "/consumer/requests/{request_id}/revoke"): CONSUMER_AUTH,
    ("connector", "GET", "/consumer/transfers"): CONSUMER_AUTH,
    ("connector", "GET", "/consumer/transfers/{transfer_id}"): CONSUMER_AUTH,
    ("connector", "GET", "/consumer/negotiations/{negotiation_id}"): CONSUMER_AUTH,
    ("connector", "GET", "/consumer/edr/{transfer_id}"): CONSUMER_AUTH,
    # The DCP and STS protocol surfaces. Their credential is a self-issued token
    # proving control of a DID, verified against that DID's document — a bearer
    # scope is the wrong shape entirely. Asserted by `dcp-trust`.
    ("identity-registry", "POST", "/sts/{did}/token"): "DCP: STS client credentials",
    ("identity-registry", "POST", "/credentials/{did}/presentations/query"): (
        "DCP: self-issued token carrying an STS grant"
    ),
    ("identity-registry", "POST", "/credentials/{did}/credentials"): (
        "DCP: issuance callback, self-issued token"
    ),
    ("identity-registry", "POST", "/issuer/credentials"): (
        "DCP: issuance request, self-issued token"
    ),
    ("identity-registry", "GET", "/issuer/requests/{issuer_pid}"): (
        "DCP: request status, self-issued token"
    ),
    # Invite-gated intake: anonymous by design, but an application without a
    # valid invite code is refused. Asserted by `org-onboarding`.
    ("identity-registry", "POST", "/onboarding/applications"): "a valid invite code",
}

# Declared `include_in_schema=False`, so they are absent from the document this
# sweep derives from and would otherwise escape it entirely. Listed by hand, and
# `tests/test_route_inventory.py` fails when a service hides a route that is not
# here — the one hole deriving from OpenAPI opens, closed from the outside.
#
# `GET /metrics` is hidden too, on all four services. It is installed by
# `ds_obs`, not by a service, and it answers **200 anonymously** — deliberately
# left out of this sweep rather than pinned as public, because that is an open
# rulebook item (Observability, `DSSC-PTO`) and not a decision.
HIDDEN_ROUTES: tuple[Route, ...] = (
    Route(
        service="connector",
        method="POST",
        template="/consent/register-transfer",
        permissions=("connector.internal",),
    ),
)

# What a probe has to send for the request to reach the credential check.
#
# **Measured, and the answer differs by mechanism.** `require_permission` is a
# FastAPI dependency, so it runs before the endpoint's own body and query
# parameters are validated: 153 of the 165 routes refuse an anonymous caller
# with 401 whatever is sent, and need nothing here. The self-authenticated
# routes check their credential *inside the handler*, so validation answers
# first — every one of them returned **422** to a bodiless probe, which is 4xx
# and would have counted as a refusal with the guard deleted.
#
# Two levels of fix, and the first covers most of it:
#
# * every write verb sends `{}` by default, because *no body at all* is a
#   different refusal from *no credential*. That alone moved the three DCP
#   endpoints from 422 to 401.
# * the rest declare the minimum their schema requires. Values are placeholders
#   — the probe must be **schema-valid and semantically nonexistent**, never
#   close enough to succeed.
#
# Forgetting an entry is loud: the route reports under `refused_before_the_guard`
# rather than passing quietly, which is why this table is safe to keep by hand
# where `_guarded_routes` was not.
PROBE_PAYLOADS: dict[tuple[str, str, str], dict[str, Any]] = {
    ("connector", "POST", "/consent/my/shares"): {
        "body": {"offer_id": PROBE_ID, "enabled": True}
    },
    ("connector", "GET", "/consent/status"): {
        "query": f"?consumer_id={PROBE_ID}&dataset_id={PROBE_ID}&subject_id={PROBE_ID}"
    },
    ("connector", "POST", "/consumer/negotiate"): {
        "body": {
            "counter_party_address": PROBE_ADDRESS,
            "offer_id": PROBE_ID,
            "asset_id": PROBE_ID,
            "assigner": PROBE_ID,
        }
    },
    ("connector", "POST", "/consumer/flow"): {
        "body": {
            "counter_party_address": PROBE_ADDRESS,
            "asset_id": PROBE_ID,
            "assigner": PROBE_ID,
        }
    },
    ("connector", "POST", "/consumer/transfer"): {
        "body": {
            "contract_agreement_id": PROBE_ID,
            "counter_party_address": PROBE_ADDRESS,
            "asset_id": PROBE_ID,
            "connector_id": PROBE_ID,
        }
    },
    ("identity-registry", "POST", "/onboarding/applications"): {
        "body": {"invite_code": PROBE_ID, "alias": PROBE_ID, "legal_name": PROBE_ID}
    },
    # OAuth2 at the STS, so the payload is form-encoded and a JSON body is a
    # 422 no matter what it contains.
    ("identity-registry", "POST", "/sts/{did}/token"): {
        "form": {
            "grant_type": "client_credentials",
            "client_id": PROBE_ID,
            "client_secret": PROBE_ID,
        }
    },
}

# A refusal that is neither 401 nor 403 did not come from a guard. 422 is the
# one to watch: it means input validation answered before authorisation was
# settled, and it counts as "4xx" to a sweep that only checks the class — which
# is how a probe passes with the guard deleted.
REFUSAL_STATUSES = (401, 403)


class ApiContractFlow(BaseFlow):
    name = "api-contract"
    description = (
        "API surface contract: public perimeter, anonymous refusal, wrong-scope "
        "refusal, input validation and error-leak checks across all services"
    )

    #: Built by `_check_route_inventory`, which runs before anything reads it.
    _inventory: list[Route] | None = None

    def execute(self) -> FlowResult:
        result = FlowResult(flow_name=self.name)

        if not self._check_health(result):
            return result

        if not self._check_route_inventory(result):
            return result

        self._check_public_perimeter(result)
        self._check_anonymous_refusal(result)
        self._check_wrong_scope_refusal(result)
        self._check_user_vc_surface(result)
        self._check_input_validation(result)
        self._check_method_discipline(result)

        return result

    # ── helpers ──────────────────────────────────────────────────────────────

    def _base(self, service: str) -> str:
        s = self.settings
        return {
            "connector": s.connector_url,
            "consumer-connector": s.consumer_connector_url,
            "identity-registry": s.identity_registry_url,
            "provenance": s.provenance_url,
            "federated-catalog": s.federated_catalog_url,
            "dataset-api": s.dataset_api_url,
        }[service]

    def _url(self, service: str, path: str) -> str:
        return f"{self._base(service)}{path}"

    def _leaks(self, body: Any) -> str | None:
        text = body if isinstance(body, str) else str(body)
        for marker in LEAK_MARKERS:
            if marker in text:
                return marker
        return None

    @staticmethod
    def _app(service: str) -> str:
        """The image behind a service name.

        `connector` and `consumer-connector` are the same app started in two
        roles, so the classification tables are keyed by this rather than by the
        endpoint they happen to be reached through.
        """
        return "connector" if service == "consumer-connector" else service

    def _key(self, route: Route) -> tuple[str, str, str]:
        """How a route is looked up in the classification tables."""
        return (self._app(route.service), route.method, route.template)

    def _is_anonymous(self, route: Route) -> bool:
        return self._key(route) in ANONYMOUS_ROUTES

    def _probe(
        self, route: Route
    ) -> tuple[str, dict[str, Any] | None, dict[str, str] | None]:
        """The URL, JSON body and form body a probe of this route must send.

        A write verb defaults to `{}` rather than to nothing: an absent body is
        a 422, and a 422 is a refusal by shape, not by credential. See
        `PROBE_PAYLOADS`.
        """
        payload = PROBE_PAYLOADS.get(self._key(route), {})
        url = self._url(route.service, route.path + payload.get("query", ""))
        body = payload.get("body")
        form = payload.get("form")
        if body is None and form is None and route.method in ("POST", "PUT", "PATCH"):
            body = {}
        return url, body, form

    def _services_this_flow_calls(self) -> list[str]:
        """Every service named by a route this flow will probe.

        **Derived, not listed** (`E2E-14`). The health gate named four services
        by hand while `PUBLIC_ROUTES` also probes `dataset-api`, so an
        unreachable data plane escaped the gate and raised `ConnectError` out of
        `_check_public_perimeter` — through `run_all`, ending the whole suite
        with a traceback and **zero** flow results. The gate exists precisely to
        turn "something is not up" into one legible failure, and it was checking
        four of the five services it went on to call.

        One list, computed from what the flow goes on to call, so a service
        added to either cannot outrun its health check.
        """
        seen: list[str] = []
        for service in list(SWEPT_SERVICES) + [svc for svc, _m, _p in PUBLIC_ROUTES]:
            if service not in seen:
                seen.append(service)
        return seen

    def _routes(self) -> list[Route]:
        """Every route the swept services publish, read once per run.

        The sweep is only as complete as this call, so a service that cannot be
        read is a failure of the flow rather than a smaller sweep — see
        `_check_route_inventory`.
        """
        if self._inventory is None:
            raise RuntimeError("route inventory not built")
        return self._inventory

    def _check_health(self, result: FlowResult) -> bool:
        services = self._services_this_flow_calls()
        for service in services:
            url = self._base(service)
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step(
                    "health",
                    f"{service} unreachable at {url}: {exc}",
                    hint=(
                        "The data plane is not started by `task docker:restart` when "
                        "it is the real celine dataset-api — see E2E-13."
                        if service == "dataset-api"
                        else None
                    ),
                )
                return False
        result.pass_step("health", f"{', '.join(services)} reachable")
        return True

    # ── 0. the route inventory ───────────────────────────────────────────────

    def _check_route_inventory(self, result: FlowResult) -> bool:
        """Read the surface from the services, and check every route is classified.

        This is the step that makes the two refusal batteries below complete.
        It fails on three things, and each is a way the old hand-kept table went
        wrong before anyone noticed:

        * **a route in no class.** Neither guarded by the app, nor declared
          anonymous, nor declared self-authenticated. It is swept anyway — the
          default is to probe — but it is reported, because an unclassified
          route means nobody decided what it should do.
        * **a stale declaration.** An entry naming a route no service publishes
          any more. That is how an exemption outlives the thing it exempted.
        * **a contradiction.** A route declared anonymous or self-authenticated
          that the app in fact guards. The declaration would exclude it from the
          wrong-scope battery, so the weaker claim would silently win.
        """
        inventory: list[Route] = list(HIDDEN_ROUTES)
        for service in SWEPT_SERVICES:
            url = self._url(service, "/openapi.json")
            status, spec = self.http.raw("GET", url)
            if status != 200 or not isinstance(spec, dict):
                result.fail_step(
                    "route inventory",
                    f"{service} does not publish its route table: {url} → {status}",
                    hint=(
                        "The sweep is derived from each service's OpenAPI document. "
                        "A deployment that sets openapi_url=None cannot be swept, "
                        "and a smaller sweep must not read as a green one."
                    ),
                )
                return False
            inventory.extend(routes_from_openapi(service, spec))
        self._inventory = inventory

        declared = set(ANONYMOUS_ROUTES) | set(SELF_AUTHENTICATED_ROUTES)
        published = {self._key(r) for r in inventory}

        unclassified = sorted(
            {
                r.label
                for r in inventory
                if not r.guarded and self._key(r) not in declared
            }
        )
        stale = sorted(f"{svc} {m} {t}" for svc, m, t in declared - published)
        contradicted = sorted(
            {
                r.label
                for r in inventory
                if r.guarded and self._key(r) in declared
            }
        )

        if unclassified or stale or contradicted:
            result.fail_step(
                "route inventory",
                "the published API surface and its classification disagree",
                unclassified=unclassified or None,
                stale_declarations=stale or None,
                declared_open_but_guarded=contradicted or None,
                published=len(inventory),
            )
            return False

        guarded = [r for r in inventory if r.guarded]
        result.pass_step(
            "route inventory",
            "every published route is guarded, or declared open with a reason",
            services=len(SWEPT_SERVICES),
            published=len(inventory),
            guarded=len(guarded),
            anonymous=len(ANONYMOUS_ROUTES),
            self_authenticated=len(SELF_AUTHENTICATED_ROUTES),
            hidden_from_openapi=len(HIDDEN_ROUTES),
        )
        return True

    # ── 1. public perimeter ──────────────────────────────────────────────────

    def _check_public_perimeter(self, result: FlowResult) -> None:
        """The anonymous surface is a decision, so it is pinned and asserted.

        These endpoints exist to be read without a credential — a DID document
        an unknown verifier must resolve, a StatusList a revocation checker must
        fetch, the ODRL vocabulary a policy engine must dereference. If one
        starts returning 401 the dataspace stops interoperating; if the list
        grows without review, the perimeter widened by accident.
        """
        s = self.settings
        routes = list(PUBLIC_ROUTES)
        # did:web resolution and StatusList are public protocol surfaces, but
        # only if the provider DID is actually registered — derive them here so
        # the pinned table above stays literal.
        encoded_did = urllib.parse.quote(s.provider_did, safe="")
        routes.append(("identity-registry", "GET", f"/dids/{encoded_did}/did.json"))

        broken: list[str] = []
        for service, method, path in routes:
            status, body = self.http.raw(method, self._url(service, path))
            if status != 200:
                broken.append(f"{service} {method} {path} → {status}")
                continue
            leak = self._leaks(body)
            if leak:
                broken.append(f"{service} {method} {path} leaks {leak!r}")
        if broken:
            result.fail_step(
                "public perimeter",
                "a route that must be publicly readable is not",
                broken=broken,
            )
            return
        result.pass_step(
            "public perimeter",
            "every intentionally-public route answers anonymously",
            routes=len(routes),
        )

    # ── 2. anonymous refusal ─────────────────────────────────────────────────

    def _check_anonymous_refusal(self, result: FlowResult) -> None:
        """No credential must mean no answer — on every route that is not open.

        Every published route except those declared anonymous above: the ones
        the app guards, and the ones that authenticate by their own mechanism.
        Both must refuse a caller carrying nothing.

        **The refusal has to be the guard's.** 401 or 403 and nothing else — a
        422 means input validation answered before authorisation was settled,
        and it is 4xx, so a sweep that only checks the class passes on it with
        the guard deleted. That is the placebo `legal_basis` was introduced to
        avoid on one route; asserting the status instead covers every route and
        needs no bodies. A 200 is an open endpoint. A 5xx is a guard that raised
        instead of denying, which is the same defect one step later.
        """
        open_routes: list[str] = []
        crashed: list[str] = []
        leaked: list[str] = []
        not_the_guard: list[str] = []

        routes = [r for r in self._routes() if not self._is_anonymous(r)]
        for route in routes:
            url, body, form = self._probe(route)
            status, payload = self.http.raw(route.method, url, body=body, form=form)
            label = f"{route.label} → {status}"
            if status < 400:
                open_routes.append(label)
            elif status >= 500:
                crashed.append(label)
            elif status not in REFUSAL_STATUSES:
                not_the_guard.append(label)
            elif self._leaks(payload):
                leaked.append(f"{route.label} leaks {self._leaks(payload)!r}")

        if open_routes or crashed or leaked or not_the_guard:
            result.fail_step(
                "anonymous refusal",
                "routes did not refuse an anonymous caller cleanly",
                unguarded=open_routes or None,
                crashed=crashed or None,
                refused_before_the_guard=not_the_guard or None,
                leaked=leaked or None,
                probed=len(routes),
            )
            return
        result.pass_step(
            "anonymous refusal",
            "every non-public route refuses an unauthenticated caller with "
            "401/403 and no leak",
            probed=len(routes),
        )

    # ── 3. wrong-scope refusal ───────────────────────────────────────────────

    def _check_wrong_scope_refusal(self, result: FlowResult) -> None:
        """A valid token is not a permit.

        Replays every permission-guarded route with a genuine Keycloak token
        from a deliberately under-privileged client. Each must still refuse.
        Both 403 (permission checked and denied) and 401 (audience rejected
        first) are correct refusals, but at least one true 403 must be observed
        — otherwise the audience check could be masking a missing permission
        check everywhere.

        **Which routes that client legitimately holds is derived, not listed.**
        The exceptions used to be eight hardcoded paths, and `AGENTS.md`
        recorded them as wrong: the realm had moved and three routes were being
        excluded from the sweep that exists to test them. The token's own
        `scope` claim is intersected with the permissions each route publishes,
        so the answer comes from the realm that issued it.

        Routes with no published requirement are out of scope here by
        construction — `/consumer/*` and the DCP endpoints decide on a
        credential that is not a bearer scope, so a refusal would prove nothing
        about permissions. `_check_anonymous_refusal` covers them.
        """
        s = self.settings
        try:
            token = self.http.token_for(s.low_priv_client_id, s.low_priv_client_secret)
        except Exception as exc:
            result.fail_step(
                "wrong-scope refusal",
                "could not obtain a low-privilege token for "
                f"'{s.low_priv_client_id}': {exc}",
            )
            return
        headers = {"Authorization": f"Bearer {token}"}

        guarded = [r for r in self._routes() if r.guarded]
        scopes = token_scopes(token)
        held = {r.key for r in routes_held_by(guarded, scopes)}
        routes = [r for r in guarded if r.key not in held]
        if not routes:
            result.fail_step(
                "wrong-scope refusal",
                f"'{s.low_priv_client_id}' holds a permission on every guarded route — "
                "it is not under-privileged and proves nothing",
                scopes=sorted(scopes),
            )
            return

        allowed: list[str] = []
        crashed: list[str] = []
        forbidden_seen = 0

        for route in routes:
            url, body, form = self._probe(route)
            status, _ = self.http.raw(
                route.method, url, body=body, form=form, headers=headers
            )
            if status < 400:
                allowed.append(f"{route.label} → {status}")
            elif status >= 500:
                crashed.append(f"{route.label} → {status}")
            elif status == 403:
                forbidden_seen += 1

        if allowed or crashed:
            result.fail_step(
                "wrong-scope refusal",
                "a token without the required scope was not refused",
                authorised_anyway=allowed or None,
                crashed=crashed or None,
                probed=len(routes),
                held_and_skipped=sorted(f"{svc} {m} {t}" for svc, m, t in held) or None,
            )
            return
        if forbidden_seen == 0:
            result.fail_step(
                "wrong-scope refusal",
                "no route answered 403 — refusals may be audience-only, leaving "
                "permission checks unverified",
                probed=len(routes),
            )
            return
        result.pass_step(
            "wrong-scope refusal",
            "an authenticated but unauthorised token is refused everywhere",
            probed=len(routes),
            explicit_403=forbidden_seen,
            held_and_skipped=len(held),
        )

    # ── 4. the user-VC surface ───────────────────────────────────────────────

    def _check_user_vc_surface(self, result: FlowResult) -> None:
        """The subject-facing API authenticates on a VC, not a bearer scope.

        `/consent/my/*` and `/consumer/*` trust `X-User-VC` + `X-Subject-Id`.
        That is a second authentication scheme and needs its own negative
        battery: absent, structurally invalid, and structurally *valid but
        forged* credentials must all be refused. The forged case is the one that
        matters — it is the only probe that proves the signature is verified
        rather than the payload merely parsed.
        """
        s = self.settings
        subject_paths = [
            ("GET", "/consent/my"),
            ("GET", "/consent/my/shares"),
            ("POST", "/consent/my/shares"),
        ]
        # A well-formed ES256 JWT whose signature is meaningless: header and a
        # DataSubject-shaped payload, signed with nothing. Accepting this would
        # mean any caller can claim to be any subject.
        forged = (
            "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJkaWQ6d2ViOnVzZXJzLmRhdGFzcGFjZXMubG9jYWxob3N0OmRhdGEtc3ViamVjdCIsInJvbGUiOiJEYXRhU3ViamVjdCJ9"
            ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        )
        cases = [
            ("no credential", {}),
            ("subject id only", {"X-Subject-Id": s.data_subject_id}),
            (
                "garbage credential",
                {"X-Subject-Id": s.data_subject_id, "X-User-VC": "not-a-jwt"},
            ),
            (
                "forged signature",
                {"X-Subject-Id": s.data_subject_id, "X-User-VC": forged},
            ),
        ]

        accepted: list[str] = []
        crashed: list[str] = []
        for case_name, headers in cases:
            for method, path in subject_paths:
                body = {"offer_id": s.sharing_offer_id, "enabled": True} if method == "POST" else None
                status, _ = self.http.raw(
                    method, self._url("connector", path), body=body, headers=headers
                )
                label = f"{case_name}: {method} {path}"
                if status < 400:
                    accepted.append(f"{label} → {status}")
                elif status >= 500:
                    crashed.append(f"{label} → {status}")

        if accepted or crashed:
            result.fail_step(
                "user-VC surface",
                "the subject-facing API accepted an invalid credential",
                accepted=accepted or None,
                crashed=crashed or None,
            )
            return
        result.pass_step(
            "user-VC surface",
            "absent, malformed and forged user credentials are all refused",
            cases=len(cases) * len(subject_paths),
        )

    # ── 5. input validation ──────────────────────────────────────────────────

    def _check_input_validation(self, result: FlowResult) -> None:
        """Bad input must produce a 4xx, never a 500.

        Each probe carries a token that *is* authorised, so the request reaches
        the handler — the assertion is about what the handler does with input it
        should not have accepted. A 500 means an unvalidated value reached the
        database, the URL parser or the JSON-LD serialiser.

        Every probe is read-only or fails at the schema layer before any write.
        """
        s = self.settings
        try:
            svc = self.http.bearer_headers()
            admin = self.http.bearer_headers_for(s.ir_admin_client_id, s.ir_admin_client_secret)
        except Exception as exc:
            result.fail_step("input validation", f"could not obtain tokens: {exc}")
            return

        traversal = urllib.parse.quote("../../etc/passwd", safe="")
        probes: list[
            tuple[str, str, str, dict[str, Any] | None, dict[str, str], set[int]]
        ] = [
            # (label, method, url, body, headers, acceptable statuses)
            (
                "paging below range",
                "GET",
                self._url("federated-catalog", "/catalog?limit=0"),
                None,
                svc,
                {422},
            ),
            (
                "paging above range",
                "GET",
                self._url("federated-catalog", "/catalog?limit=100000"),
                None,
                svc,
                {422},
            ),
            (
                "negative offset",
                "GET",
                self._url("federated-catalog", "/catalog?offset=-1"),
                None,
                svc,
                {422},
            ),
            (
                "unknown lineage direction",
                "GET",
                self._url("provenance", "/prov/lineage/urn:e2e:x?direction=sideways"),
                None,
                svc,
                {422},
            ),
            (
                "lineage depth above range",
                "GET",
                self._url("provenance", "/prov/lineage/urn:e2e:x?max_depth=9999"),
                None,
                svc,
                {422},
            ),
            (
                "audit summary missing required filter",
                "GET",
                self._url("provenance", "/audit/log/summary"),
                None,
                svc,
                {422},
            ),
            (
                "consent check missing required params",
                "GET",
                self._url("connector", "/internal/consent/check"),
                None,
                svc,
                {422},
            ),
            (
                "unparseable timestamp filter",
                "GET",
                self._url("provenance", "/audit/log?from=not-a-date"),
                None,
                svc,
                {422},
            ),
            (
                "wrong body type",
                "POST",
                self._url("federated-catalog", "/catalog/search"),
                {"q": {"nested": "object"}, "limit": "many"},
                svc,
                {422},
            ),
            (
                "unknown dataset on ingestion",
                "POST",
                self._url("connector", "/admin/ingestion"),
                {"dataset_id": "datasets.does.not.exist"},
                svc,
                {422},
            ),
            (
                "ingestion with wrong field type",
                "POST",
                self._url("connector", "/admin/ingestion"),
                {"dataset_id": s.asset_id, "record_count": "lots"},
                svc,
                {422},
            ),
            (
                "organisation application missing required fields",
                "POST",
                self._url("identity-registry", "/admin/organizations/applications"),
                {"alias": "e2e-invalid"},
                admin,
                {422},
            ),
            # Traversal-shaped path parameters. These route through {path}
            # converters that accept slashes, so the assertion is that they
            # resolve to "not found", never to a file or a crash.
            (
                "traversal in DID path",
                "GET",
                self._url("identity-registry", f"/dids/{traversal}/did.json"),
                None,
                {},
                {400, 404, 422},
            ),
            (
                "traversal in provenance IRI",
                "GET",
                self._url("provenance", f"/prov/entities/{traversal}"),
                None,
                svc,
                {400, 404, 422},
            ),
            (
                "traversal in catalog IRI",
                "GET",
                self._url("federated-catalog", f"/catalog/{traversal}"),
                None,
                svc,
                {400, 404, 422},
            ),
        ]

        wrong: list[str] = []
        crashed: list[str] = []
        leaked: list[str] = []
        for label, method, url, body, headers, acceptable in probes:
            status, payload = self.http.raw(method, url, body=body, headers=headers)
            if status >= 500:
                crashed.append(f"{label} → {status}")
                continue
            leak = self._leaks(payload)
            if leak:
                leaked.append(f"{label} leaks {leak!r}")
            if status not in acceptable:
                wrong.append(f"{label} → {status} (expected {sorted(acceptable)})")

        if crashed or leaked:
            result.fail_step(
                "input validation",
                "invalid input reached application code instead of being rejected",
                crashed=crashed or None,
                leaked=leaked or None,
                probed=len(probes),
            )
            return
        if wrong:
            result.fail_step(
                "input validation",
                "invalid input was not rejected with the expected status",
                mismatched=wrong,
                probed=len(probes),
            )
            return
        result.pass_step(
            "input validation",
            "malformed, out-of-range and traversal-shaped input is rejected with a 4xx",
            probed=len(probes),
        )

    # ── 6. method discipline ─────────────────────────────────────────────────

    def _check_method_discipline(self, result: FlowResult) -> None:
        """A read-only route must not answer a write verb.

        Cheap, but it catches the case where a router is mounted with a wildcard
        or a proxy rewrites verbs — both of which turn a public read surface
        into a write one.
        """
        probes = [
            ("connector", "POST", "/ns/policy"),
            ("connector", "DELETE", "/ns/sharing-offers"),
            ("provenance", "POST", "/prov/context"),
            ("federated-catalog", "POST", "/catalog/meta"),
            ("identity-registry", "POST", "/health"),
        ]
        wrong: list[str] = []
        for service, method, path in probes:
            status, _ = self.http.raw(method, self._url(service, path), body={})
            if status != 405:
                wrong.append(f"{service} {method} {path} → {status} (expected 405)")
        if wrong:
            result.fail_step(
                "method discipline",
                "a read-only route answered a write verb",
                mismatched=wrong,
            )
            return
        result.pass_step(
            "method discipline",
            "write verbs on read-only routes return 405",
            probed=len(probes),
        )
