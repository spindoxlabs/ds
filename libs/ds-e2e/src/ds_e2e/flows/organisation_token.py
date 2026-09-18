"""An organisation acting as itself — ADR-0014, rulebook `D-20` (amended).

Every other exchange flow has a person at the keyboard: a `ConsumerUser`
credential drives `/consumer/*`. This one drives the same routes with **the
consumer organisation's own client token** (`svc-ds-connector-<alias>`, `sub` =
its participant context, `scope` in EDC's `management-api:…` grammar), the way a
batch job does:

    catalogue → negotiate → agreement → transfer → EDR (from the callback) → data

and then asks what that token must **not** reach:

- another participant's organisation token on this connector — `403`, whatever
  it holds, because the token names another participant context;
- a realm token that is not an organisation's, holding a ds permission — `403`
  on a route that needs EDC's scope. A ds permission is not EDC's scope;
- no token at all — `401`;
- a person's consents (`/consent/my/*`) — `401`: the organisation token is not a
  subject credential (`D-20`);
- this organisation's EDC management API from the host — **unreachable**. EDC
  never checks a management token's audience, so an unpublished port is the
  control, and this is the live half of `test_management_port_isolation.py`.

It also asserts the act is attributable (`XCT-09`): the consumer's provenance
holds the principal that acted, with the client id that acted.

**Not asserted live: a genuine organisation token that lacks one EDC scope.**
Every organisation client carries its seven management scopes as default
scopes, and a `client_credentials` request cannot drop a default scope, so the
dev realm holds no such token. The connector's unit suite covers it
(`services/connector/tests/test_organisation_actor.py`).

Target: the REC's `datasets.gold.om_weather_features` — membership-gated, not
consent-gated, served by the mock data plane only (the data step always asks the
mock, and names it). The flow revokes its own earlier requests for it before it
starts and after it ends, so it re-runs in place, and it never touches a
person's requests (the ledger keys the organisation apart).
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import time
import urllib.parse
from typing import Any

import httpx

from ds_e2e.config import describe_data_plane
from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
FINAL_TRANSFER_STATES = {"STARTED"}
#: The purpose declared and queried with. The offer publishes it; the flow
#: checks that rather than trusting this constant.
PURPOSE = "GridMonitoring"
REASON = "e2e-organisation-token"
#: How long provenance may take to materialise a fire-and-forget event.
PROVENANCE_WAIT_S = 15.0


def _edc_runs_in_docker() -> bool:
    """Is the provider EDC a container, or a host JVM?

    The same question `fail-closed` asks about the connector, and the same way:
    ask Docker for a **running** container by name. `dev:*` replaces the EDCs with
    host processes, and a port they bind says nothing about whether a deployment
    would publish it.

    Docker being absent or unreadable answers *not in Docker*, which downgrades a
    step to a skip rather than failing a run for a tool this harness does not
    require.
    """
    try:
        proc = subprocess.run(
            ["docker", "ps", "--filter", "name=^dataspaces-edc-rec-1$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and "dataspaces-edc-rec-1" in proc.stdout


def _claims(token: str) -> dict[str, Any]:
    """A JWT's payload, unverified — only to name what the realm issued."""
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
        return claims
    except (IndexError, ValueError):
        return {}


class OrganisationTokenFlow(BaseFlow):
    name = "organisation-token"
    description = (
        "The consumer organisation's own client token drives catalogue → "
        "negotiation → transfer → data, and is refused everywhere it is not its own"
    )
    rules = ("D-20", "L-5")

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        if not self._check_health(result):
            return result

        try:
            token = self.http.token_for(
                s.consumer_org_client_id, s.consumer_org_client_secret
            )
        except Exception as exc:
            result.fail_step(
                "organisation token",
                f"{s.consumer_org_client_id} could not authenticate — run "
                f"`ir-cli keycloak org-sync` (task identity:bootstrap): {exc}",
            )
            return result
        claims = _claims(token)
        if claims.get("sub") != s.consumer_did:
            result.fail_step(
                "organisation token",
                "the organisation client's `sub` is not its participant context — "
                "the `participant-context-sub` mapper is missing or wrong",
                sub=claims.get("sub"),
                expected=s.consumer_did,
            )
            return result
        result.pass_step(
            "organisation token",
            "the consumer organisation's client names its participant context",
            client_id=s.consumer_org_client_id,
            sub=claims.get("sub"),
        )
        headers = {"Authorization": f"Bearer {token}"}

        self._check_refusals(result, headers)
        self._check_management_port(result)

        if not self._clear(result, headers, "no earlier request of its own"):
            return result
        agreement = self._negotiate(result, headers)
        if agreement is None:
            return result
        self._check_attribution(result, claims)
        transfer = self._transfer(result, headers, agreement)
        if transfer is None:
            return result
        self._query(result, headers, agreement, transfer)
        self._clear(result, headers, "revoke its own request")
        return result

    def cleanup(self) -> None:
        """Revoke anything `execute` left open, on the exception path too."""
        s = self.settings
        try:
            token = self.http.token_for(
                s.consumer_org_client_id, s.consumer_org_client_secret
            )
        except Exception:
            return
        self._revoke_own({"Authorization": f"Bearer {token}"})

    # ── what the token must not reach ────────────────────────────────────────

    def _check_refusals(self, result: FlowResult, org_headers: dict[str, str]) -> None:
        s = self.settings
        catalog = f"{s.consumer_connector_url}/consumer/catalog"
        catalog_body = {
            "counter_party_address": s.counter_party_address,
            "counter_party_id": s.provider_did,
        }
        negotiate = f"{s.consumer_connector_url}/consumer/negotiate"
        negotiate_body = {
            "counter_party_address": s.counter_party_address,
            "offer_id": f"{s.organisation_asset_id}#offer",
            "asset_id": s.organisation_asset_id,
            "assigner": s.provider_did,
            "declared_purpose": [PURPOSE],
            "justification_ref": REASON,
        }

        # Another organisation's token: authentic, fully scoped, not this
        # participant's.
        try:
            other = self.http.bearer_headers_for(
                s.provider_org_client_id, s.provider_org_client_secret
            )
        except Exception as exc:
            result.fail_step("another participant's token", str(exc))
            other = None
        if other is not None:
            refused = {
                "catalog": self.http.raw(
                    "POST", catalog, body=catalog_body, headers=other
                )[0],
                "negotiate": self.http.raw(
                    "POST", negotiate, body=negotiate_body, headers=other
                )[0],
                "requests": self.http.raw(
                    "GET",
                    f"{s.consumer_connector_url}/consumer/requests",
                    headers=other,
                )[0],
            }
            if any(code != 403 for code in refused.values()):
                result.fail_step(
                    "another participant's token",
                    "a token naming another participant context was not refused "
                    "with 403",
                    statuses=refused,
                )
            else:
                result.pass_step(
                    "another participant's token",
                    f"{s.provider_org_client_id} is refused on the consumer's "
                    "routes: its `sub` is another participant",
                    statuses=refused,
                )

        # A realm token that is not an organisation's. `svc-ds-e2e` holds
        # `connector.consumer.read` among much else — a ds permission, not EDC's
        # scope, and not an organisation.
        try:
            service = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("a ds permission is not EDC's scope", str(exc))
            service = None
        if service is not None:
            status, body = self.http.raw(
                "POST", negotiate, body=negotiate_body, headers=service
            )
            if status != 403:
                result.fail_step(
                    "a ds permission is not EDC's scope",
                    "a non-organisation service token started a negotiation path",
                    status_code=status,
                    body=body,
                )
            else:
                result.pass_step(
                    "a ds permission is not EDC's scope",
                    "a realm service token that is not an organisation's is "
                    "refused on /consumer/negotiate",
                )

        status, _ = self.http.raw("POST", negotiate, body=negotiate_body)
        if status != 401:
            result.fail_step(
                "no credential",
                "an anonymous negotiation was not a 401",
                status_code=status,
            )
        else:
            result.pass_step("no credential", "an anonymous negotiation is a 401")

        # D-20: never a person's consents.
        consent = {
            path: self.http.raw(
                "GET", f"{s.consumer_connector_url}{path}", headers=org_headers
            )[0]
            for path in ("/consent/my", "/consent/my/shares")
        }
        consent["provider /consent/my"] = self.http.raw(
            "GET", f"{s.connector_url}/consent/my", headers=org_headers
        )[0]
        if any(code != 401 for code in consent.values()):
            result.fail_step(
                "never a person's consents",
                "an organisation token was not refused on a subject surface",
                statuses=consent,
            )
        else:
            result.pass_step(
                "never a person's consents",
                "the organisation token is not a subject credential: 401 on "
                "/consent/my/*, at the consumer and at the provider",
                statuses=consent,
            )

    def _check_management_port(self, result: FlowResult) -> None:
        urls = self.settings.edc_management_host_urls
        if not urls:
            result.skip_step(
                "management port unreachable",
                "E2E_EDC_MANAGEMENT_HOST_URLS is empty — set for `dev:*`, whose "
                "EDCs are host JVMs. Not asserted in this run.",
            )
            return
        answered: dict[str, int] = {}
        for url in urls:
            probe = f"{url.rstrip('/')}/management/v5beta/participants/x/assets/request"
            try:
                status, _ = self.http.raw("POST", probe, body={})
            except httpx.TransportError:
                # Refused, unroutable or timed out: nothing answers here.
                continue
            answered[url] = status
        if answered and not _edc_runs_in_docker():
            # **`dev:*`, where the EDCs are host JVMs.** They bind the management
            # port on the host by construction — `task edc-rec:watch` runs the fat
            # JAR directly — so the property this step asserts is one only the
            # container topology can have. Failing here would make `e2e:all`
            # permanently red in dev, and a suite with a standing red line is one
            # people stop reading; that is the reasoning `fail-closed` already
            # writes out at length for the same situation.
            #
            # Detected rather than configured. The setting could be cleared by
            # hand for a dev run, and was not: the default is non-empty, nothing
            # sets it, and the step failed for a property of the topology rather
            # than of the platform. A check that needs a variable nobody sets is a
            # check that runs in one mode.
            result.skip_step(
                "management port unreachable",
                "the EDCs are host JVMs in this topology (`task dev:*`), so they "
                "listen on the host by construction — the unpublished-port control "
                "is a property of the container topology and is asserted there. "
                "Not evidence either way in this run.",
                answered=answered,
            )
            return
        if answered:
            result.fail_step(
                "management port unreachable",
                "an EDC management API answers from the host. EDC does not check a "
                "token's audience, so any holder of an organisation token can "
                "administer that organisation's contracts from here (ADR-0014)",
                answered=answered,
            )
            return
        result.pass_step(
            "management port unreachable",
            "no EDC management API answers on the host",
            probed=list(urls),
        )

    # ── the exchange ─────────────────────────────────────────────────────────

    def _negotiate(self, result: FlowResult, headers: dict[str, str]) -> str | None:
        s = self.settings
        asset_id = s.organisation_asset_id
        try:
            catalog = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/catalog",
                    {
                        "counter_party_address": s.counter_party_address,
                        "counter_party_id": s.provider_did,
                    },
                    headers=headers,
                )
                or {}
            )
        except Exception as exc:
            result.fail_step("catalogue", str(exc))
            return None
        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        dataset = next(
            (
                d
                for d in datasets
                if isinstance(d, dict)
                and str(d.get("@id") or d.get("id") or "") == asset_id
            ),
            None,
        )
        if dataset is None:
            result.fail_step(
                "catalogue",
                f"the provider's catalogue does not offer {asset_id} to the "
                "organisation",
                published=sorted(
                    str(d.get("@id") or d.get("id"))
                    for d in datasets
                    if isinstance(d, dict)
                ),
            )
            return None
        policy = self._policy(dataset)
        purposes = [
            p for p in self._offer_purposes(policy) if p.rsplit("/", 1)[-1] == PURPOSE
        ]
        if not purposes:
            result.fail_step(
                "catalogue",
                f"the offer for {asset_id} no longer permits {PURPOSE}",
                purposes=self._offer_purposes(policy),
            )
            return None
        result.pass_step(
            "catalogue",
            "the organisation token reads the provider's catalogue over DSP",
            asset_id=asset_id,
        )

        try:
            negotiated = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/negotiate",
                    {
                        "counter_party_address": s.counter_party_address,
                        "offer_id": str(policy.get("@id") or f"{asset_id}#offer"),
                        "asset_id": asset_id,
                        "assigner": s.provider_did,
                        "odrl_policy": policy or None,
                        "declared_purpose": purposes,
                        "justification_ref": REASON,
                    },
                    headers=headers,
                )
                or {}
            )
            negotiation_id = str(negotiated["negotiation_id"])
        except Exception as exc:
            result.fail_step("negotiate", str(exc))
            return None

        encoded = urllib.parse.quote(negotiation_id, safe="")
        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/negotiations/{encoded}",
            lambda p: (
                p.get("state") in FINAL_NEGOTIATION_STATES
                and bool(p.get("contractAgreementId"))
            ),
            headers=headers,
        )
        agreement_id = state.get("contractAgreementId")
        if not agreement_id:
            result.fail_step(
                "negotiate",
                "the organisation's negotiation did not finalize",
                negotiation_id=negotiation_id,
                state=state.get("state"),
                error=state.get("errorDetail") or state.get("detail"),
            )
            return None
        result.pass_step(
            "negotiate",
            "an agreement for the organisation itself, with no person named",
            negotiation_id=negotiation_id,
            agreement_id=agreement_id,
        )

        requests = (
            self.http.get(
                f"{s.consumer_connector_url}/consumer/requests", headers=headers
            )
            or []
        )
        recorded = next(
            (
                r
                for r in requests
                if isinstance(r, dict) and r.get("negotiation_id") == negotiation_id
            ),
            None,
        )
        if recorded is None:
            result.fail_step(
                "the ledger keeps the organisation's request",
                "the organisation's own request is not listed for it",
            )
            return None
        result.pass_step(
            "the ledger keeps the organisation's request",
            "listed for the organisation token, apart from any person's",
            request_id=recorded.get("id"),
        )
        return str(agreement_id)

    def _check_attribution(self, result: FlowResult, claims: dict[str, Any]) -> None:
        """`XCT-09`: the act names the client that acted."""
        s = self.settings
        iri = f"urn:ds:principal:{claims.get('iss')}:{claims.get('sub')}"
        url = (
            f"{s.consumer_provenance_url}/prov/agents/"
            f"{urllib.parse.quote(iri, safe='')}"
        )
        deadline = time.monotonic() + PROVENANCE_WAIT_S
        body: Any = None
        status = 0
        while time.monotonic() < deadline:
            status, body = self.http.raw("GET", url, headers=self.http.bearer_headers())
            if status == 200:
                break
            time.sleep(1.0)
        nodes = body.get("@graph") if isinstance(body, dict) else None
        node = (nodes or [body])[0] if status == 200 else None
        client_id = node.get("clientId") if isinstance(node, dict) else None
        if client_id != s.consumer_org_client_id:
            result.fail_step(
                "the act names its client",
                "the consumer's provenance does not hold the organisation "
                "principal with its client id",
                agent=iri,
                status_code=status,
                client_id=client_id,
            )
            return
        result.pass_step(
            "the act names its client",
            "provenance records the organisation principal and the client that acted",
            agent=iri,
            client_id=client_id,
        )

    def _transfer(
        self, result: FlowResult, headers: dict[str, str], agreement_id: str
    ) -> str | None:
        s = self.settings
        try:
            started = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/transfer",
                    {
                        "contract_agreement_id": agreement_id,
                        "counter_party_address": s.counter_party_address,
                        "asset_id": s.organisation_asset_id,
                        "connector_id": s.provider_did,
                    },
                    headers=headers,
                )
                or {}
            )
            transfer_id = str(started["transfer_id"])
        except Exception as exc:
            result.fail_step("transfer", str(exc))
            return None
        encoded = urllib.parse.quote(transfer_id, safe="")
        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/transfers/{encoded}",
            lambda p: p.get("state") in FINAL_TRANSFER_STATES,
            headers=headers,
        )
        if state.get("state") not in FINAL_TRANSFER_STATES:
            result.fail_step(
                "transfer",
                "the organisation's transfer did not start",
                transfer_id=transfer_id,
                state=state.get("state"),
            )
            return None
        result.pass_step("transfer", "the transfer started", transfer_id=transfer_id)
        return transfer_id

    def _query(
        self,
        result: FlowResult,
        headers: dict[str, str],
        agreement_id: str,
        transfer_id: str,
    ) -> None:
        s = self.settings
        encoded = urllib.parse.quote(transfer_id, safe="")
        status, edr = self.http.raw(
            "GET",
            f"{s.consumer_connector_url}/consumer/edr/{encoded}",
            headers=headers,
        )
        token = str((edr or {}).get("authorization") or "") if status == 200 else ""
        if not token:
            result.fail_step(
                "EDR from the callback",
                "the connector holds no EDR for the organisation's transfer — "
                "did the EDC reach CONNECTOR_EDC_CALLBACK_URL?",
                status_code=status,
                body=edr,
            )
            return
        result.pass_step(
            "EDR from the callback",
            "the EDC delivered the EDR to the connector's callback",
            endpoint=(edr or {}).get("endpoint"),
        )

        # The mock, always: the target dataset is served by
        # `services/dataset-api-mock` only (the real celine plane is seeded with
        # `datasets.silver.meters_15m` alone), so asking the real plane would fail
        # for a reason unrelated to the organisation token.
        plane = s.mock_data_plane_url
        status, payload = self.http.post_raw(
            f"{plane}/query",
            {"sql": f"SELECT * FROM {s.organisation_asset_id}", "limit": 10},
            headers={
                "Authorization": token,
                "Edc-Contract-Agreement-Id": str(
                    (edr or {}).get("agreement_id") or agreement_id
                ),
                "Edc-Transfer-Process-Id": transfer_id,
                "Edc-Purpose": PURPOSE,
            },
        )
        rows = payload.get("count", 0) if isinstance(payload, dict) else 0
        if status != 200 or rows < 1:
            result.fail_step(
                "data",
                f"the query was not answered with rows ({describe_data_plane(plane)})",
                status_code=status,
                body=payload,
            )
            return
        result.pass_step(
            "data",
            f"rows returned to the organisation ({describe_data_plane(plane)})",
            rows=rows,
        )

    # ── housekeeping ─────────────────────────────────────────────────────────

    def _revoke_own(self, headers: dict[str, str]) -> tuple[list[str], str | None]:
        s = self.settings
        status, requests = self.http.raw(
            "GET", f"{s.consumer_connector_url}/consumer/requests", headers=headers
        )
        if status != 200 or not isinstance(requests, list):
            return [], f"could not list its requests ({status}): {requests!r}"
        revoked: list[str] = []
        for item in requests:
            if not isinstance(item, dict) or not item.get("can_revoke"):
                continue
            if item.get("asset_id") != s.organisation_asset_id:
                continue
            request_id = str(item.get("id") or "")
            encoded = urllib.parse.quote(request_id, safe="")
            status, body = self.http.raw(
                "POST",
                f"{s.consumer_connector_url}/consumer/requests/{encoded}/revoke",
                body={"reason": REASON},
                headers=headers,
            )
            if status != 200 or (body or {}).get("status") != "revoked":
                return revoked, f"revoke of {request_id} answered {status}: {body!r}"
            revoked.append(request_id)
        return revoked, None

    def _clear(self, result: FlowResult, headers: dict[str, str], step: str) -> bool:
        revoked, error = self._revoke_own(headers)
        if error:
            result.fail_step(step, error, revoked=revoked or None)
            return False
        result.pass_step(
            step,
            "the organisation's own requests for the asset are revoked",
            revoked=revoked,
        )
        return True
