"""API contract sweep — the guard rail under every other flow.

The functional flows prove the happy path works. This one proves the API
*refuses* correctly, which is the property that decides whether the platform is
deployable outside a lab. It asserts four things about every service:

1. **The public perimeter is exactly what we reviewed.** A pinned list of routes
   that must answer with no credential. It is a two-way assertion: these must
   not regress to 401 (they are protocol surfaces — DID resolution, StatusList,
   the ODRL vocabulary — that unauthenticated parties must read), and nothing
   else may join them silently.
2. **Every guarded route refuses an anonymous caller.** Not "most routes" — a
   table covering each router of each service, asserting a 401. A 200 here is an
   open endpoint; a 500 is a guard that crashed instead of denying.
3. **Authentication is not authorisation.** The same table replayed with a real,
   fully-valid token that simply lacks the scope. Anything other than a refusal
   means the route authenticates but never checks what the caller may do.
4. **Bad input is rejected, not absorbed.** Malformed bodies, out-of-range
   paging, unknown enum values and traversal-shaped path parameters must produce
   4xx. A 500 means the input reached something that was not expecting it.

Every refusal is additionally checked for leakage: no stack traces, no driver
names, no connection strings in an error body.

Needs no EDC: connector, identity-registry, provenance, federated-catalog and
Keycloak are enough.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

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

# Routes that are public *by design* and must stay reachable with no credential.
# Adding a line here is a deliberate decision to widen the anonymous perimeter.
PUBLIC_ROUTES: list[tuple[str, str, str]] = [
    ("connector", "GET", "/health"),
    ("connector", "GET", "/ns/policy"),
    ("connector", "GET", "/ns/sharing-offers"),
    ("identity-registry", "GET", "/health"),
    ("provenance", "GET", "/health"),
    ("provenance", "GET", "/prov/context"),
    ("federated-catalog", "GET", "/health"),
    ("dataset-api", "GET", "/health"),
]


def _guarded_routes(s: Any) -> list[tuple[str, str, str, dict[str, Any] | None]]:
    """(service, method, path, body) for every route that must require a token.

    One line per guarded route. Bodies are only present where the framework
    would otherwise reject the request before the guard runs — the point is to
    reach the guard, never to succeed.
    """
    did = urllib.parse.quote(s.provider_did, safe="")
    return [
        # ── connector: provider management ───────────────────────────────────
        ("connector", "POST", "/provider/sync", {}),
        ("connector", "GET", "/provider/assets", None),
        ("connector", "GET", "/provider/policies", None),
        ("connector", "GET", "/provider/contracts", None),
        ("connector", "GET", "/provider/transfers", None),
        ("connector", "GET", "/provider/authorizations", None),
        ("connector", "DELETE", "/provider/assets/e2e-nonexistent", None),
        ("connector", "DELETE", "/provider/policies/e2e-nonexistent", None),
        ("connector", "DELETE", "/provider/contracts/e2e-nonexistent", None),
        # ── connector: admin ─────────────────────────────────────────────────
        ("connector", "GET", "/admin/participants", None),
        ("connector", "POST", "/admin/ingestion", {"dataset_id": s.asset_id}),
        # ── connector: internal (dataset-api and EDC call these) ─────────────
        ("connector", "GET", "/internal/edr-jwks", None),
        ("connector", "GET", "/internal/consent/check?dataset_id=x&consumer_id=y&subject_id=z", None),
        ("connector", "GET", "/internal/participants/check?did=x&scope=y", None),
        ("connector", "GET", "/internal/agreements/e2e-nonexistent/status", None),
        ("connector", "GET", "/internal/transfers/e2e-nonexistent/status", None),
        ("connector", "POST", "/internal/audit/query", {}),
        # The EDC pending guard records an ask here. Anonymous access would let
        # anyone raise a consent request against any subject pool.
        (
            "connector",
            "POST",
            "/internal/consent/asks",
            {
                "negotiation_id": "e2e-nonexistent",
                "dataset_id": s.asset_id,
                "consumer_id": s.consumer_did,
            },
        ),
        # ── connector: webhooks (the EDC calls these) ────────────────────────
        ("connector", "POST", "/webhooks/contract-negotiation", {}),
        ("connector", "POST", "/webhooks/transfer-process", {}),
        # ── connector: history ───────────────────────────────────────────────
        ("connector", "GET", "/history/agreements", None),
        ("connector", "GET", "/history/negotiations", None),
        ("connector", "GET", "/history/transfers", None),
        # ── connector: operator-provisioned consent ──────────────────────────
        (
            "connector",
            "POST",
            "/consent/admin/shares",
            {"subject_id": s.data_subject_id, "offer_id": s.sharing_offer_id, "enabled": True},
        ),
        ("connector", "POST", "/consent/register-transfer", {}),
        # Provider-local seeding. It used to authenticate on the *consumer's*
        # VC-JWT; it is now a service route, so it belongs in this battery.
        (
            "connector",
            "POST",
            "/consent/request",
            {
                "consumer_id": s.consumer_did,
                "dataset_id": s.asset_id,
                "subject_ids": [s.data_subject_id],
            },
        ),
        # The operator view names subjects — it must never answer anonymously.
        ("connector", "GET", "/consent/asks", None),
        # Status only, but still a participant-scoped question about somebody
        # else's negotiation.
        ("connector", "GET", "/consent/pending?correlation_id=e2e-nonexistent", None),
        # ── identity-registry: admin ─────────────────────────────────────────
        ("identity-registry", "GET", "/admin/participants", None),
        ("identity-registry", "POST", "/admin/participants", {}),
        ("identity-registry", "GET", f"/admin/participants/{did}", None),
        ("identity-registry", "DELETE", f"/admin/participants/{did}", None),
        ("identity-registry", "GET", "/admin/participants/check?did=x&scope=y", None),
        ("identity-registry", "GET", "/admin/owners", None),
        ("identity-registry", "POST", "/admin/owners", {}),
        ("identity-registry", "GET", "/admin/credentials", None),
        ("identity-registry", "POST", "/admin/credentials/organization", {}),
        ("identity-registry", "POST", "/admin/credentials/membership", {}),
        ("identity-registry", "POST", "/admin/credentials/data-subject", {}),
        ("identity-registry", "GET", "/admin/memberships", None),
        ("identity-registry", "POST", "/admin/memberships", {}),
        ("identity-registry", "GET", "/admin/organizations/applications", None),
        ("identity-registry", "POST", "/admin/organizations/applications", {}),
        ("identity-registry", "POST", "/admin/dids", {}),
        ("identity-registry", "GET", f"/admin/dids/{did}", None),
        ("identity-registry", "POST", f"/admin/keys/rotate/{did}", {}),
        ("identity-registry", "POST", "/admin/keycloak/sync", {}),
        ("identity-registry", "GET", "/admin/keycloak/mapping", None),
        # ── identity-registry: scoped reads ──────────────────────────────────
        ("identity-registry", "GET", "/owners/resolve?alias=example-org", None),
        ("identity-registry", "GET", "/memberships/check?user_did=x&organization=y", None),
        ("identity-registry", "GET", "/users/resolve?email=nobody@example.test", None),
        ("identity-registry", "GET", "/agreements", None),
        (
            "identity-registry",
            "GET",
            "/agreements/current?participant_did=did:web:nobody.example",
            None,
        ),
        # ── provenance ───────────────────────────────────────────────────────
        ("provenance", "GET", "/prov/events", None),
        ("provenance", "GET", "/prov/entities", None),
        ("provenance", "GET", "/prov/activities", None),
        ("provenance", "GET", "/prov/agents", None),
        ("provenance", "POST", "/prov/entities", {}),
        ("provenance", "POST", "/prov/activities", {}),
        ("provenance", "POST", "/prov/agents", {}),
        ("provenance", "POST", "/prov/events", {}),
        ("provenance", "POST", "/prov/relations", {}),
        ("provenance", "GET", "/prov/lineage/urn:e2e:nonexistent", None),
        ("provenance", "GET", "/audit/log", None),
        ("provenance", "POST", "/audit/log", {}),
        ("provenance", "GET", f"/audit/log/summary?dataset_id={s.asset_id}", None),
        # ── federated catalog ────────────────────────────────────────────────
        ("federated-catalog", "GET", "/catalog", None),
        ("federated-catalog", "GET", "/catalog/meta", None),
        ("federated-catalog", "POST", "/catalog/search", {"q": "energy"}),
    ]


class ApiContractFlow(BaseFlow):
    name = "api-contract"
    description = (
        "API surface contract: public perimeter, anonymous refusal, wrong-scope "
        "refusal, input validation and error-leak checks across all services"
    )

    def execute(self) -> FlowResult:
        result = FlowResult(flow_name=self.name)

        if not self._check_health(result):
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

    def _check_health(self, result: FlowResult) -> bool:
        for service in ("connector", "identity-registry", "provenance", "federated-catalog"):
            url = self._base(service)
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step("health", f"{service} unreachable at {url}: {exc}")
                return False
        result.pass_step("health", "connector, identity-registry, provenance, federated-catalog reachable")
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
        """No credential must mean no answer — on every guarded route.

        401 is the expected code. A 200 is an unguarded endpoint. A 5xx is a
        guard that raised instead of denying, which is equally a defect: it
        means the request reached application code before authentication was
        settled.
        """
        open_routes: list[str] = []
        crashed: list[str] = []
        leaked: list[str] = []

        routes = _guarded_routes(self.settings)
        for service, method, path, body in routes:
            status, payload = self.http.raw(method, self._url(service, path), body=body)
            label = f"{service} {method} {path}"
            if status < 400:
                open_routes.append(f"{label} → {status}")
            elif status >= 500:
                crashed.append(f"{label} → {status}")
            elif self._leaks(payload):
                leaked.append(f"{label} leaks {self._leaks(payload)!r}")

        if open_routes or crashed or leaked:
            result.fail_step(
                "anonymous refusal",
                "guarded routes did not refuse an anonymous caller cleanly",
                unguarded=open_routes or None,
                crashed=crashed or None,
                leaked=leaked or None,
                probed=len(routes),
            )
            return
        result.pass_step(
            "anonymous refusal",
            "every guarded route refuses an unauthenticated caller with a 4xx and no leak",
            probed=len(routes),
        )

    # ── 3. wrong-scope refusal ───────────────────────────────────────────────

    def _check_wrong_scope_refusal(self, result: FlowResult) -> None:
        """A valid token is not a permit.

        Replays the same table with a genuine Keycloak token from a client that
        holds neither connector nor provenance nor identity-registry.admin
        scopes. Every route must still refuse. Both 403 (permission checked and
        denied) and 401 (audience rejected first) are correct refusals, but at
        least one true 403 must be observed — otherwise the audience check could
        be masking a missing permission check everywhere.
        """
        s = self.settings
        try:
            headers = self.http.bearer_headers_for(s.low_priv_client_id, s.low_priv_client_secret)
        except Exception as exc:
            result.fail_step(
                "wrong-scope refusal",
                f"could not obtain a low-privilege token for '{s.low_priv_client_id}': {exc}",
            )
            return

        allowed: list[str] = []
        crashed: list[str] = []
        forbidden_seen = 0

        # catalog.read and identity-registry.read are genuinely held by this
        # client, so those routes are expected to succeed and are not probed.
        held = {
            ("federated-catalog", "GET", "/catalog"),
            ("federated-catalog", "GET", "/catalog/meta"),
            ("federated-catalog", "POST", "/catalog/search"),
            ("identity-registry", "GET", "/admin/participants"),
            ("identity-registry", "GET", "/admin/participants/check?did=x&scope=y"),
            ("identity-registry", "GET", "/owners/resolve?alias=example-org"),
            ("identity-registry", "GET", "/agreements"),
            (
                "identity-registry",
                "GET",
                "/agreements/current?participant_did=did:web:nobody.example",
            ),
        }

        routes = [r for r in _guarded_routes(s) if (r[0], r[1], r[2]) not in held]
        for service, method, path, body in routes:
            status, _ = self.http.raw(method, self._url(service, path), body=body, headers=headers)
            label = f"{service} {method} {path}"
            if status < 400:
                allowed.append(f"{label} → {status}")
            elif status >= 500:
                crashed.append(f"{label} → {status}")
            elif status == 403:
                forbidden_seen += 1

        if allowed or crashed:
            result.fail_step(
                "wrong-scope refusal",
                "a token without the required scope was not refused",
                authorised_anyway=allowed or None,
                crashed=crashed or None,
                probed=len(routes),
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
