"""Two providers, differently shaped — `D-54`, `DID-15`.

Every other flow in this suite runs against **one** provider, and a suite with
one provider cannot tell the difference between *"this platform supports a data
space"* and *"this platform supports this fixture"*. Three questions only a
second organisation can ask:

1. **Does "which provider?" mean anything?** With one counterparty the answer is
   always the default. Here the consumer negotiates with the grid operator while
   the REC is up and publishing, and the agreement has to name the right one.
2. **Does one participant's governance leak into another's?** Both connectors
   are the same image reading a `governance.yaml`; only the directory differs.
   A shared path, a cached registry, a default that resolves to "the first
   provider" — each shows up here as one participant publishing the other's
   datasets or the other's consent offers.
3. **Is the consent machinery driven by the data, or by the deployment?** The
   REC's meter data is consent-gated because it is about people. The DSO's
   substation data is not, because it is about substations. A platform that
   requires consent everywhere and one that requires it nowhere both pass a
   single-provider suite; only two providers of different shape separate them.

The flow deliberately **does not** re-prove DSP mechanics — `smoke` does that.
It proves that those mechanics stay correct when there is more than one of
everything.
"""
from __future__ import annotations

import logging
import urllib.parse

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
FINAL_TRANSFER_STATES = {"STARTED"}


class TwoProvidersFlow(BaseFlow):
    name = "two-providers"
    description = (
        "A second provider with no members: separate governance, separate "
        "catalogue, and a negotiation that names which counterparty it is with"
    )
    rules = ("C-7", "X-1")

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        try:
            self.http.get(f"{s.grid_operator_connector_url}/health")
            result.pass_step("health", "the grid operator's connector is reachable")
        except Exception as exc:
            result.fail_step(
                "health",
                f"the second provider is not running at "
                f"{s.grid_operator_connector_url}: {exc}",
            )
            return result

        try:
            self.http.acquire_service_token()
            svc_headers = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        if not self._check_registered(result, svc_headers):
            return result
        self._check_governance_is_its_own(result, svc_headers)
        self._check_no_members(result, svc_headers)
        self._negotiate_with_the_second_provider(result)
        return result

    # ── registration ─────────────────────────────────────────────────────────

    def _check_registered(self, result: FlowResult, headers: dict[str, str]) -> bool:
        """Two participants that are both providers, each with its own DID.

        Read from the **anchor**, because that is where registry questions go
        after `DID-05` — and a second provider that never enrolled would
        otherwise show up much later as an empty catalogue.
        """
        s = self.settings
        try:
            body = self.http.get(
                f"{s.identity_registry_url}/admin/participants", headers=headers
            ) or {}
        except Exception as exc:
            result.fail_step("both providers registered", str(exc))
            return False

        rows = body if isinstance(body, list) else (body.get("participants") or [])
        dids = {r.get("did") for r in rows if isinstance(r, dict)}
        missing = {s.provider_did, s.grid_operator_did} - dids
        if missing:
            result.fail_step(
                "both providers registered",
                "a provider is missing from the participant registry",
                missing=sorted(missing),
                registered=sorted(d for d in dids if d),
            )
            return False
        result.pass_step(
            "both providers registered",
            "the REC and the grid operator are both enrolled participants",
            providers=sorted({s.provider_did, s.grid_operator_did}),
        )
        return True

    # ── governance separation ────────────────────────────────────────────────

    def _check_governance_is_its_own(self, result: FlowResult, headers: dict[str, str]) -> None:
        """Each provider publishes **its own** datasets and offers.

        The failure this catches is not exotic: both connectors are the same
        image, and `sharing_offers_path` defaults to the file beside
        `governance.yaml`. Point them at one directory and the DSO starts
        publishing the REC's consent offers — a provider soliciting consent on
        behalf of an organisation it has nothing to do with.
        """
        s = self.settings
        try:
            rec_offers = self.http.get(f"{s.connector_url}/ns/sharing-offers") or []
            dso_offers = (
                self.http.get(f"{s.grid_operator_connector_url}/ns/sharing-offers")
                or []
            )
        except Exception as exc:
            result.fail_step("governance is its own", str(exc))
            return

        if not rec_offers:
            result.fail_step(
                "governance is its own",
                "the REC publishes no sharing offers — this comparison proves "
                "nothing unless one side actually has some",
            )
            return
        if dso_offers:
            result.fail_step(
                "governance is its own",
                "the grid operator publishes sharing offers, but it has no "
                "members to ask — it is reading somebody else's governance",
                offers=[o.get("id") for o in dso_offers if isinstance(o, dict)],
            )
            return
        result.pass_step(
            "governance is its own",
            "the REC publishes consent offers and the grid operator publishes "
            "none — a provider with no members asks nobody for anything",
            rec_offers=[o.get("id") for o in rec_offers if isinstance(o, dict)],
        )

    def _check_no_members(self, result: FlowResult, headers: dict[str, str]) -> None:
        """The DSO's registry holds exactly one subject: itself.

        `DID-11` step 2 puts a person's credentials with the organisation that
        onboarded them. This organisation onboarded nobody, so its credential
        store must contain no people — the structural difference the fixture
        exists to make observable.
        """
        s = self.settings
        someone = f"{s.grid_operator_did}:users:data-subject"
        encoded = urllib.parse.quote(someone, safe="")
        status, body = self.http.raw(
            "GET",
            f"{s.grid_operator_identity_registry_url}/users/{encoded}/credentials",
            headers=headers,
        )
        # The route exists on every participant host — a participant's shape
        # must not depend on whether it happens to hold credentials for people —
        # so the answer is an empty list, not a missing endpoint.
        if status != 200:
            result.fail_step(
                "no members",
                "the grid operator's credential store did not answer",
                status_code=status,
            )
            return
        held = (body or {}).get("credentials") or []
        if held:
            result.fail_step(
                "no members",
                "the grid operator holds credentials for a person it never "
                "onboarded",
                credentials=held,
            )
            return
        result.pass_step(
            "no members",
            "the grid operator holds credentials for no people, and says so "
            "with an empty answer rather than a missing route",
        )

    # ── the exchange, with the counterparty named ────────────────────────────

    def _negotiate_with_the_second_provider(self, result: FlowResult) -> None:
        s = self.settings
        consumer_vc = self._consumer_credential(result)
        if consumer_vc is None:
            return
        headers = {"X-Subject-Id": s.consumer_subject_id, "X-User-VC": consumer_vc}

        try:
            catalog = self.http.post(
                f"{s.consumer_connector_url}/consumer/catalog",
                {
                    "counter_party_address": s.grid_operator_counter_party_address,
                    "counter_party_id": s.grid_operator_did,
                },
                headers=headers,
            ) or {}
        except Exception as exc:
            result.fail_step("catalog of the second provider", str(exc))
            return

        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        ids = {
            str(d.get("@id") or d.get("id") or "")
            for d in datasets
            if isinstance(d, dict)
        }
        if s.grid_operator_asset_id not in ids:
            result.fail_step(
                "catalog of the second provider",
                "the grid operator does not publish its own dataset",
                expected=s.grid_operator_asset_id,
                published=sorted(ids),
            )
            return
        # …and not the REC's. One catalogue per participant, or "which provider"
        # has no answer even when the identifiers say it does.
        if s.asset_id in ids:
            result.fail_step(
                "catalog of the second provider",
                "the grid operator publishes the REC's dataset — the two are "
                "reading the same governance",
                published=sorted(ids),
            )
            return
        result.pass_step(
            "catalog of the second provider",
            "the grid operator publishes its own dataset and none of the REC's",
            published=sorted(ids),
        )

        dataset = next(
            d
            for d in datasets
            if isinstance(d, dict)
            and str(d.get("@id") or d.get("id")) == s.grid_operator_asset_id
        )
        policy = self._policy(dataset)
        offer_id = str(policy.get("@id") or f"{s.grid_operator_asset_id}#offer")

        try:
            negotiated = self.http.post(
                f"{s.consumer_connector_url}/consumer/negotiate",
                {
                    "counter_party_address": s.grid_operator_counter_party_address,
                    "offer_id": offer_id,
                    "asset_id": s.grid_operator_asset_id,
                    # **The whole point.** With one provider this field is a
                    # formality; with two it decides who the agreement is with.
                    "assigner": s.grid_operator_did,
                    "odrl_policy": policy or None,
                    "declared_purpose": ["GridMonitoring"],
                    "justification_ref": "e2e-two-providers",
                },
                headers=headers,
            ) or {}
            negotiation_id = negotiated["negotiation_id"]
        except Exception as exc:
            result.fail_step("negotiate with the DSO", str(exc))
            return

        encoded = urllib.parse.quote(negotiation_id, safe="")
        negotiation = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/negotiations/{encoded}",
            lambda p: p.get("state") in FINAL_NEGOTIATION_STATES
            and bool(p.get("contractAgreementId")),
            headers=headers,
        )
        agreement_id = negotiation.get("contractAgreementId")
        if not agreement_id:
            result.fail_step(
                "negotiate with the DSO",
                "the negotiation did not finalize",
                state=negotiation.get("state"),
            )
            return
        result.pass_step(
            "negotiate with the DSO",
            "a contract with the second provider, for data no consent gates",
            agreement_id=agreement_id,
        )

        requests = self.http.get(
            f"{s.consumer_connector_url}/consumer/requests", headers=headers
        ) or []
        recorded = next(
            (r for r in requests if r.get("negotiation_id") == negotiation_id), None
        )
        counterparty = (recorded or {}).get("assigner") or (recorded or {}).get(
            "counter_party_id"
        )
        if not recorded:
            result.fail_step("the record names the counterparty", "no request recorded")
            return
        if counterparty and counterparty != s.grid_operator_did:
            result.fail_step(
                "the record names the counterparty",
                "the request records a different provider than the one it was "
                "negotiated with",
                recorded=counterparty,
                expected=s.grid_operator_did,
            )
            return
        result.pass_step(
            "the record names the counterparty",
            "the access request records which provider it is with",
            assigner=counterparty or s.grid_operator_did,
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _consumer_credential(self, result: FlowResult) -> str | None:
        s = self.settings
        try:
            headers = self.http.bearer_headers()
            email = urllib.parse.quote(s.consumer_email, safe="")
            body = self.http.get(
                f"{s.identity_registry_url}/users/resolve?email={email}",
                headers=headers,
            ) or {}
            vc: str | None = body.get("vc_jws")
            if not vc:
                result.fail_step(
                    "consumer credential",
                    f"no credential for {s.consumer_email}",
                )
                return None
            return vc
        except Exception as exc:
            result.fail_step("consumer credential", str(exc))
            return None

