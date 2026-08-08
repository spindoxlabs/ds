"""User authority — do a human's role bundles authorise the API, and only that?

Every other flow in this harness authenticates with `client_credentials`, which
authorises on the `scope` claim. A *human* authorises on `groups`, expanded
through the role bundles in `ds_auth.bundles` — a different branch of
`Principal.authority`, and one that had **no API-level coverage at all**: the unit
tests prove the expansion in isolation and Playwright proves the UI gates on it,
but nothing proved a real Keycloak-issued user token reaches (and fails to reach)
the endpoints the bundle says it should.

That gap mattered because the group vocabulary was replaced wholesale: ~30 groups
named after scopes became four bundles plus `ds-member`. A mistake there is
invisible until an operator either cannot do their job or can do somebody else's.

Four properties, each asserted positively *and* negatively — a permission model
is only as good as what it refuses:

- **The seat works.** A bundle holder reaches the endpoints its capabilities name.
- **The seat is bounded.** The same holder is refused the endpoints it does not.
- **Machine identity is unreachable.** No user token, *including the operator's*,
  satisfies `connector.internal` — it is `require_exact_permission`, so even the
  `connector.admin` superset inside `ds-admin` must not open it. This is the
  assertion that would catch a bundle table edit that looked harmless.
- **Bundle names are not scopes.** A user token carrying `ds-participant-admin`
  must not authorise anything if the expansion were ever removed — asserted
  indirectly by requiring the *expanded* capability to work while the
  bundle-shaped name is meaningless as a scope (see `test_bundles.py` for the
  service-token half).

Needs no EDC: connector, identity-registry and federated-catalog are enough.

**What this flow does not prove.** Dev services run with no OIDC issuer
configured, so `ds_auth` accepts tokens without signature or audience
verification (`oidc_insecure_dev`). The tokens here are genuinely issued by
Keycloak, but the assertions are about *authorisation*, not about JWKS or
audience handling — that path is covered by `libs/ds-auth/tests/test_verify.py`.
"""
from __future__ import annotations

import logging

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

# Anything other than 401/403 counts as "reached the handler": a 404 or a 502
# means authorisation passed and the request then failed on its own merits,
# which is what these assertions are about. Coupling them to 200 would make the
# flow fail whenever an unrelated dependency was down.
_REFUSED = (401, 403)


class UserAuthorityFlow(BaseFlow):
    name = "user-authority"
    description = (
        "A human's role bundles authorise exactly their seat: positive reach, "
        "bounded refusal, and no path to a machine identity"
    )

    def execute(self) -> FlowResult:  # noqa: C901 — a table of assertions
        s = self.settings
        result = FlowResult(flow_name=self.name)

        try:
            self.http.get(f"{s.connector_url}/health")
            result.pass_step("health", "connector reachable")
        except Exception as exc:
            result.fail_step("health", str(exc))
            return result

        # Four seats, from the dev realm's group assignments.
        seats: dict[str, dict[str, str]] = {}
        try:
            seats["ds-admin"] = self.http.user_headers(s.admin_email, s.admin_password)
            seats["ds-participant-admin"] = self.http.user_headers(
                s.provider_email, s.provider_password
            )
            seats["ds-member/consumer"] = self.http.user_headers(
                s.consumer_email, s.consumer_password
            )
            seats["ds-member/subject"] = self.http.user_headers(
                s.data_subject_email, s.data_subject_password
            )
            result.pass_step(
                "user tokens", f"password grant issued for {len(seats)} dev users"
            )
        except Exception as exc:
            # A failure here is a fixture problem, not a policy finding — say so,
            # because "no token" would otherwise make every refusal below pass.
            result.fail_step(
                "user tokens",
                f"could not obtain user tokens (client={s.user_client_id}): {exc}",
            )
            return result

        # A token that authorises but identifies nobody is a realm-configuration
        # failure that looks like success everywhere else: `Principal.subject` is
        # empty, and every provenance attribution of a human act is recorded as "".
        # In Keycloak the cause is a login client missing the `basic` client scope,
        # which is what puts `sub` in an **access** token (the ID token has it
        # regardless, so a browser flow hides this entirely).
        import base64
        import json as _json

        for seat, headers in seats.items():
            payload = headers["Authorization"].split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = _json.loads(base64.urlsafe_b64decode(payload))
            if claims.get("sub"):
                result.pass_step(
                    f"{seat} token identifies its subject", "carries a `sub` claim"
                )
            else:
                result.fail_step(
                    f"{seat} token identifies its subject",
                    "the access token carries no `sub` — add the `basic` client "
                    f"scope to {s.user_client_id}; every act by this seat would be "
                    "recorded as performed by nobody",
                )

        assets = f"{s.connector_url}/provider/assets"
        negotiations = f"{s.connector_url}/history/negotiations"
        applications = f"{s.identity_registry_url}/admin/organizations/applications"
        catalog_meta = f"{s.federated_catalog_url}/catalog/meta"
        edr_jwks = f"{s.connector_url}/internal/edr-jwks"
        sync = f"{s.connector_url}/provider/sync"

        def reaches(step: str, seat: str, method: str, url: str, why: str) -> None:
            status, body = self.http.raw(method, url, headers=seats[seat])
            if status in _REFUSED:
                result.fail_step(
                    step,
                    f"{seat} was refused {method} {url} ({status}) but its bundle "
                    f"grants {why}: {str(body)[:200]}",
                )
            else:
                result.pass_step(step, f"{seat} reaches {why} ({status})")

        def refused(step: str, seat: str, method: str, url: str, why: str) -> None:
            status, body = self.http.raw(method, url, headers=seats[seat])
            if status in _REFUSED:
                result.pass_step(step, f"{seat} is refused {why} ({status})")
            else:
                result.fail_step(
                    step,
                    f"{seat} reached {method} {url} ({status}) but its bundle does "
                    f"not grant {why}: {str(body)[:200]}",
                )

        # ── The seat works ───────────────────────────────────────────────────
        #
        # `ds-participant-admin` → connector.provider.read + connector.history.read
        reaches(
            "participant reads assets",
            "ds-participant-admin",
            "GET",
            assets,
            "connector.provider.read",
        )
        reaches(
            "participant reads history",
            "ds-participant-admin",
            "GET",
            negotiations,
            "connector.history.read",
        )
        # `ds-admin` holds `connector.admin`, a superset over every `connector.*`.
        reaches("operator reads assets", "ds-admin", "GET", assets, "connector.admin")
        # …and `identity-registry.admin`, which covers the onboarding queue.
        reaches(
            "operator reads applications",
            "ds-admin",
            "GET",
            applications,
            "identity-registry.admin",
        )
        # `ds-member` → catalog.read, and that is the whole seat.
        reaches(
            "member reads catalogue",
            "ds-member/consumer",
            "GET",
            catalog_meta,
            "catalog.read",
        )

        # ── The seat is bounded ──────────────────────────────────────────────
        #
        # The onboarding queue is the operator surface a participant's own
        # administrator must not see: `ds-participant-admin` carries no
        # `identity-registry.organizations.*`.
        refused(
            "participant cannot review applications",
            "ds-participant-admin",
            "GET",
            applications,
            "identity-registry.organizations.read",
        )
        # A data subject or consumer has no provider console. Asserted with the
        # *write* endpoint as well as the read one, because a 403 mutates nothing
        # and the write path is the one that would matter.
        refused(
            "member cannot read assets",
            "ds-member/subject",
            "GET",
            assets,
            "connector.provider.read",
        )
        refused(
            "member cannot sync the provider",
            "ds-member/subject",
            "POST",
            sync,
            "connector.provider.write",
        )
        refused(
            "member cannot review applications",
            "ds-member/consumer",
            "GET",
            applications,
            "identity-registry.organizations.read",
        )

        # ── Authority is confined to the caller's own owner ──────────────────
        #
        # `connector.provider.write` says what a caller may do; it never said whose
        # data they may do it to. The connector's unit tests prove the guard with
        # synthetic claims; this proves the **wiring** — a real Keycloak token, a
        # real organisation claim, and a real owner alias resolved through the
        # registry.
        #
        # The two assertions are a pair on purpose. A 403 on its own would also be
        # produced by a token that is simply not authorised, which would make this
        # pass for the wrong reason; so the same seat is first shown to reach the
        # provider surface it *is* entitled to.
        try:
            other_owner = self.http.user_headers(
                s.grid_operator_email, s.grid_operator_password
            )
        except Exception as exc:
            result.fail_step(
                "cross-owner seat",
                f"could not obtain a token for {s.grid_operator_email}: {exc}",
            )
            return result

        status, body = self.http.raw("GET", assets, headers=other_owner)
        if status in _REFUSED:
            result.fail_step(
                "cross-owner seat is authorised at all",
                f"{s.other_org} operator was refused {assets} ({status}) — the "
                f"refusal below would then prove nothing: {str(body)[:200]}",
            )
        else:
            result.pass_step(
                "cross-owner seat is authorised at all",
                f"{s.other_org} operator reaches the provider surface ({status})",
            )

        # A refused DELETE mutates nothing, so this is safe to assert in place.
        status, body = self.http.raw(
            "DELETE", f"{s.connector_url}/provider/assets/{s.asset_id}",
            headers=other_owner,
        )
        if status in _REFUSED:
            result.pass_step(
                "cross-owner write is refused",
                f"{s.other_org} operator cannot delete an asset owned by "
                f"{s.owning_org} ({status})",
            )
        elif status >= 500:
            # A 5xx here is **not** evidence either way, and reading it as one
            # cost a session: on a stack whose provider EDC was down this step
            # reported "was allowed to delete" — a P1-shaped failure whose cause
            # was an outage. Worse, the same outage is what made the perimeter
            # allow the request in the first place (`ENV-09`), so the two
            # failures arrive together and the harness pointed at the wrong one.
            #
            # It fails rather than skips, because a provider surface that cannot
            # answer is a real problem — but it says which problem.
            result.fail_step(
                "cross-owner write is refused",
                f"the provider surface answered {status}, so the refusal could "
                "not be observed: this says nothing about owner scoping. Check "
                "the provider EDC is up before reading this as a fail-open",
                detail_body=str(body)[:200],
            )
        else:
            result.fail_step(
                "cross-owner write is refused",
                f"{s.other_org} operator deleted or was allowed to delete "
                f"{s.asset_id}, owned by {s.owning_org} ({status}): "
                f"{str(body)[:200]}",
            )

        # ── Layer B: a foreign IdP's group name is translated ────────────────
        #
        # `legacy-provider-admin` is not a ds bundle. Unaliased it falls through to
        # pass-through and grants only itself, which matches no call site — so this
        # seat can reach the provider surface **only** if the deployment's alias map
        # turned it into `ds-participant-admin`.
        #
        # Paired with a bound: the same seat must still be refused something the
        # bundle does not contain. Translation that granted more than the bundle
        # would be a permission table in deployment config, which is the thing the
        # Layer A/B split exists to prevent.
        try:
            legacy = self.http.user_headers(
                s.legacy_operator_email, s.legacy_operator_password
            )
        except Exception as exc:
            result.fail_step(
                "aliased seat", f"could not obtain a token for {s.legacy_operator_email}: {exc}"
            )
            return result

        status, body = self.http.raw("GET", assets, headers=legacy)
        if status in _REFUSED:
            result.fail_step(
                "foreign group is translated",
                f"a seat holding only `legacy-provider-admin` was refused {assets} "
                f"({status}) — the alias map did not translate it: {str(body)[:200]}",
            )
        else:
            result.pass_step(
                "foreign group is translated",
                f"`legacy-provider-admin` reaches the provider surface as "
                f"ds-participant-admin ({status})",
            )

        status, body = self.http.raw("GET", applications, headers=legacy)
        if status in _REFUSED:
            result.pass_step(
                "translation is bounded",
                f"the aliased seat gets the bundle and no more ({status})",
            )
        else:
            result.fail_step(
                "translation is bounded",
                f"the aliased seat reached the onboarding queue ({status}), which "
                f"ds-participant-admin does not grant: {str(body)[:200]}",
            )

        # ── Machine identity is unreachable ──────────────────────────────────
        #
        # `/internal/edr-jwks` is guarded by `require_exact_permission
        # ("connector.internal")`. `ds-admin` holds `connector.admin`, which
        # satisfies any `connector.*` under the superset rule — so if the exact
        # rule ever regressed, the operator seat would hand out the data-plane
        # signing keys. No bundle may contain a machine-identity permission, and
        # no superset may substitute for one.
        for seat in seats:
            refused(
                f"no machine identity for {seat}",
                seat,
                "GET",
                edr_jwks,
                "connector.internal (exact)",
            )

        return result
