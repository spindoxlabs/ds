"""An offer visible only to the organisations it names — the access policy.

A provider that says *this dataset goes to these organisations and to nobody
else* used to say it as ``Membership eq owner:<alias>:partner``: a string the
trust anchor kept by hand, that no enrolment ever granted, and that was checked
by one HTTP call per negotiation beside a signed ``MembershipCredential`` that
already carried the answer. It said nothing, so the datasets asking for it could
be negotiated by nobody and the reason was invisible
(``the-owner-scope-is-a-string-nobody-grants``).

It is an ODRL ``odrl:recipient`` constraint now — *"the party receiving the
result/outcome of exercising the action of the Rule"* (ODRL 2.2 Common
Vocabulary) — carrying participant DIDs, in the ContractDefinition's **access**
policy. EDC evaluates that policy with a ``CatalogPolicyContext`` at two moments:
when it builds a catalogue for a counterparty
(``ContractDefinitionResolverImpl``) and again when that counterparty opens a
negotiation (``ContractValidationServiceImpl.validateInitialOffer``). So the
restriction *hides* rather than refusing late, and refuses anyone who asks by id
regardless.

## Why two datasets

One proves nothing. A restriction that hides everything looks exactly like one
that works, and a restriction that hides nothing looks exactly like one that is
not evaluated — the shape of failure this suite keeps finding is the check that
never ran. So the REC publishes a pair, both ``access_requirements: partner``,
both ``green`` with a contract-based offer so the consent gate is legitimately
absent and nothing else is being measured:

- ``datasets.gold.flex_forecast`` — recipient ``consumer-org``, which **is** the
  dev consumer. Visible, and negotiable.
- ``datasets.gold.grid_forecast`` — recipient ``grid-operator``, which is not.
  Absent from the consumer's catalogue, and refused when asked for by id.

The visible half runs first, because "not in the catalogue" alone is satisfiable
by a dataset that was never published, by a sync that did not run, and by a typo.
A restriction that hides everything and one that is not evaluated at all are
indistinguishable without it.

**The catalogue step is the provider-side assertion.** Filtering a *published*
dataset out of a catalogue is something only `ContractDefinitionResolverImpl`
evaluating the access policy can do, and it is the same policy, the same context
and the same binding that `ContractValidationServiceImpl.validateInitialOffer`
re-evaluates when a negotiation opens. The by-id step that follows it is weaker
and says so: it observes that this consumer cannot even form a request, because
an offer id is the provider's to mint.

## What this does not assert

The catalogue consequence, stated in ``docs/services/federated-catalog.md``: the
federated crawler sees what **its own** identity is a recipient of, because it
crawls through the consumer connector. ``catalog-discovery`` asserts that from
the other side — that the restricted-away dataset is not in the federated
catalogue either — so it is not repeated here.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}

#: States a refused negotiation settles in: the provider ended it without an
#: agreement, which is what an unfulfilled access policy produces.
#:
#: `REQUESTED` is **not** here. It is the state a negotiation sits in while the
#: provider is still deciding — and while a consent-gated one is parked — so
#: treating it as a refusal would let `_settle` return before the provider had
#: answered, passing the negative half against a negotiation that was about to
#: succeed. A negotiation that never leaves it is reported by the poll timing
#: out, which is the honest answer.
REFUSED_STATES = {"TERMINATED", "TERMINATING"}


class RecipientRestrictionFlow(BaseFlow):
    name = "recipient-restriction"
    description = (
        "A dataset restricted to named recipients: visible and negotiable to a "
        "recipient, hidden from and refused to everyone else"
    )
    rules = ("C-21", "A-11", "D-14")

    #: A well-formed ODRL Set, taken from the dataset this consumer *is* a
    #: recipient of, and reused for the by-id attempt below. See
    #: `_assert_refused_by_id` for why the attempt needs one at all.
    _stand_in_policy: dict[str, Any] | None = None

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        consumer_vc = self._consumer_credential(result)
        if consumer_vc is None:
            return result
        headers = {"X-Subject-Id": s.consumer_subject_id, "X-User-VC": consumer_vc}

        catalog = self._catalog(result, headers)
        if catalog is None:
            return result
        datasets = self._datasets(catalog)
        published = {
            str(d.get("@id") or d.get("id") or "")
            for d in datasets
            if isinstance(d, dict)
        }

        if not self._assert_visible(result, published, s.recipient_asset_id):
            return result
        if not self._assert_hidden(result, published, s.non_recipient_asset_id):
            return result
        if not self._clear_requests(result, headers):
            return result

        self._assert_negotiable(result, headers, datasets, s.recipient_asset_id)
        self._assert_no_usable_offer(result, headers, s.non_recipient_asset_id)
        return result

    # ── inputs ───────────────────────────────────────────────────────────────

    def _consumer_credential(self, result: FlowResult) -> str | None:
        s = self.settings
        try:
            self.http.acquire_service_token()
            email = urllib.parse.quote(s.consumer_email, safe="")
            body = (
                self.http.get(
                    f"{s.identity_registry_url}/users/resolve?email={email}",
                    headers=self.http.bearer_headers(),
                )
                or {}
            )
        except Exception as exc:  # noqa: BLE001 — any failure is the same verdict
            result.fail_step("consumer credential", str(exc))
            return None
        vc = body.get("vc_jws")
        if not vc:
            result.fail_step(
                "consumer credential",
                f"no credential for {s.consumer_email} — the consumer cannot ask "
                "the provider anything, so nothing below would mean 'restricted'",
            )
            return None
        return str(vc)

    def _catalog(
        self, result: FlowResult, headers: dict[str, str]
    ) -> dict[str, Any] | None:
        s = self.settings
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
        except Exception as exc:  # noqa: BLE001
            result.fail_step("provider catalogue", str(exc))
            return None
        return catalog

    @staticmethod
    def _datasets(catalog: dict[str, Any]) -> list[Any]:
        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        return [datasets] if isinstance(datasets, dict) else list(datasets)

    # ── the two directions ───────────────────────────────────────────────────

    def _assert_visible(
        self, result: FlowResult, published: set[str], asset_id: str
    ) -> bool:
        """The control. Without it, "hidden" is indistinguishable from "empty"."""
        if asset_id not in published:
            result.fail_step(
                "a recipient sees its dataset",
                f"{asset_id} is not in this consumer's catalogue, although the "
                "consumer is the recipient its offer names. Either the access "
                "policy is denying a recipient, or the provider never published "
                "it — and until this passes the negative half proves nothing",
                published=sorted(published),
            )
            return False
        result.pass_step(
            "a recipient sees its dataset",
            f"{asset_id} is offered to the consumer, which its offer names as "
            "the recipient",
        )
        return True

    def _assert_hidden(
        self, result: FlowResult, published: set[str], asset_id: str
    ) -> bool:
        if asset_id in published:
            result.fail_step(
                "a non-recipient sees nothing",
                f"{asset_id} is restricted to another organisation and is in "
                "this consumer's catalogue anyway — the access policy is not "
                "being evaluated in the catalog scope",
                published=sorted(published),
            )
            return False
        result.pass_step(
            "a non-recipient sees nothing",
            f"{asset_id} is restricted to an organisation this consumer is not, "
            "and does not appear in its catalogue",
        )
        return True

    def _assert_negotiable(
        self,
        result: FlowResult,
        headers: dict[str, str],
        datasets: list[Any],
        asset_id: str,
    ) -> None:
        s = self.settings
        dataset = next(
            (
                d
                for d in datasets
                if isinstance(d, dict) and str(d.get("@id") or d.get("id")) == asset_id
            ),
            None,
        )
        policy = self._policy(dataset or {})
        self._stand_in_policy = policy or None
        offer_id = str(policy.get("@id") or f"{asset_id}#offer")

        negotiation_id = self._negotiate(
            headers, asset_id, offer_id, policy, declared_purpose=["FlexibilityResearch"]
        )
        if negotiation_id is None:
            result.fail_step(
                "a recipient may negotiate",
                "the consumer's own connector refused to open the negotiation, "
                "so the provider never answered",
            )
            return

        state = self._settle(headers, negotiation_id)
        if not state.get("contractAgreementId"):
            result.fail_step(
                "a recipient may negotiate",
                "a named recipient was refused a contract",
                state=state.get("state"),
            )
            return
        result.pass_step(
            "a recipient may negotiate",
            "the recipient holds a contract for the restricted dataset",
            agreement_id=state.get("contractAgreementId"),
        )

    def _assert_no_usable_offer(
        self, result: FlowResult, headers: dict[str, str], asset_id: str
    ) -> None:
        """The second half of hiding: there is no offer to negotiate with either.

        A consumer that already knows the asset id — from a shared document, an
        older catalogue, a guess — still cannot open a negotiation for it. EDC
        identifies an offer by a `ContractOfferId` the **provider** mints
        (`<definition>:<asset>:<uuid>`, base64 per part, the uuid fresh per
        catalogue render), and `ds_edc.NegotiationRequest` refuses a request whose
        `offer_id` is not the `@id` of the policy it carries: *the offer sent to a
        provider must be the offer it published*. The only source of that id is a
        catalogue this consumer is excluded from.

        **What this step is, and what it is not.** It is evidence that the
        restriction leaves no usable handle, taken from *this* side of the
        exchange. It is **not** evidence about the provider's decision, and it is
        reported as what it is — the provider-side half is the catalogue step
        above, where `ContractDefinitionResolverImpl` evaluating the access policy
        is the only thing that can remove a published dataset from a catalogue,
        and EDC re-evaluates that same policy in
        `ContractValidationServiceImpl.validateInitialOffer`. That the operand is
        bound in the one scope both moments use is asserted where it can be:
        `PolicyRegistrationTest` and `AccessPolicyFunctionsTest`.
        """
        negotiation_id = self._negotiate(
            headers,
            asset_id,
            f"{asset_id}#offer",
            policy=self._stand_in_policy,
            declared_purpose=None,
        )
        if negotiation_id is None:
            result.pass_step(
                "a non-recipient has no offer to negotiate with",
                "the request could not be formed: an offer id is the provider's "
                "to mint and must match the policy it carries, and the only "
                "catalogue that would supply one excludes this consumer",
            )
            return

        state = self._settle(headers, negotiation_id)
        if state.get("contractAgreementId"):
            result.fail_step(
                "a non-recipient has no offer to negotiate with",
                f"a contract was agreed for {asset_id}, which names another "
                "organisation as its recipient",
                agreement_id=state.get("contractAgreementId"),
            )
            return
        result.pass_step(
            "a non-recipient has no offer to negotiate with",
            "the negotiation reached the provider and no contract was agreed for "
            "a dataset this consumer is not a recipient of",
            state=state.get("state"),
        )

    # ── re-runnability (`REV-03`) ────────────────────────────────────────────

    def _clear_requests(self, result: FlowResult, headers: dict[str, str]) -> bool:
        """Revoke this consumer's live requests for the two assets.

        Not tidiness. The connector deduplicates access requests per user and
        asset, so a second run answers its own negotiation with

            409 "Access for asset '…' was already requested by this user"

        which `_negotiate` reports as *not started* — indistinguishable from the
        provider refusing. The flow passed the first time and failed the second
        for a reason that had nothing to do with recipients, which is exactly the
        confusion `fail-closed` documents at length.

        The predicate is the connector's own `can_revoke`, not a copy of its
        status set here: a second holder of that vocabulary drifts the moment the
        connector adds a status.
        """
        s = self.settings
        assets = {s.recipient_asset_id, s.non_recipient_asset_id}
        try:
            requests = (
                self.http.get(
                    f"{s.consumer_connector_url}/consumer/requests", headers=headers
                )
                or []
            )
        except Exception as exc:  # noqa: BLE001
            result.fail_step("prior requests cleared", str(exc))
            return False

        revoked: list[str] = []
        for item in requests:
            if not isinstance(item, dict) or item.get("asset_id") not in assets:
                continue
            if not item.get("can_revoke"):
                continue
            request_id = str(item.get("id") or "")
            if not request_id:
                continue
            encoded = urllib.parse.quote(request_id, safe="")
            try:
                body = (
                    self.http.post(
                        f"{s.consumer_connector_url}/consumer/requests/{encoded}/revoke",
                        {"reason": "e2e-recipient-restriction"},
                        headers=headers,
                    )
                    or {}
                )
            except Exception as exc:  # noqa: BLE001
                result.fail_step(
                    "prior requests cleared", f"could not revoke {request_id}: {exc}"
                )
                return False
            if body.get("status") != "revoked":
                result.fail_step(
                    "prior requests cleared",
                    f"revoke of {request_id} answered {body.get('status')!r}",
                )
                return False
            revoked.append(request_id)

        result.pass_step(
            "prior requests cleared",
            "this consumer holds no live access request for either dataset, so "
            "the negotiations below reach the provider rather than a 409",
            revoked=revoked or None,
        )
        return True

    # ── plumbing ─────────────────────────────────────────────────────────────

    @staticmethod
    def _policy(dataset: dict[str, Any]) -> dict[str, Any]:
        policy = dataset.get("hasPolicy") or dataset.get("odrl:hasPolicy") or {}
        if isinstance(policy, list):
            policy = policy[0] if policy else {}
        return policy if isinstance(policy, dict) else {}

    def _negotiate(
        self,
        headers: dict[str, str],
        asset_id: str,
        offer_id: str,
        policy: dict[str, Any] | None,
        declared_purpose: list[str] | None = None,
    ) -> str | None:
        s = self.settings
        request: dict[str, Any] = {
            "counter_party_address": s.counter_party_address,
            "offer_id": offer_id,
            "asset_id": asset_id,
            "assigner": s.provider_did,
            "odrl_policy": policy or None,
            "justification_ref": "e2e-recipient-restriction",
        }
        if declared_purpose:
            request["declared_purpose"] = declared_purpose
        try:
            body = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/negotiate",
                    request,
                    headers=headers,
                )
                or {}
            )
        except Exception as exc:  # noqa: BLE001 — a refusal here is reported, not raised
            log.info("recipient-restriction: negotiation not started: %s", exc)
            return None
        negotiation_id = body.get("negotiation_id")
        return str(negotiation_id) if negotiation_id else None

    def _settle(self, headers: dict[str, str], negotiation_id: str) -> dict[str, Any]:
        """Poll until the negotiation settles, and report whatever it settled as.

        A refusal is not an exception: `poll_until` times out on a negotiation
        that never agrees, and the timeout *is* the answer. The final read is
        what gets reported, so the step says the state rather than asserting one.
        """
        s = self.settings
        encoded = urllib.parse.quote(negotiation_id, safe="")
        url = f"{s.consumer_connector_url}/consumer/negotiations/{encoded}"
        try:
            return (
                self.http.poll_until(
                    url,
                    lambda p: bool(p.get("contractAgreementId"))
                    or str(p.get("state")) in REFUSED_STATES,
                    headers=headers,
                )
                or {}
            )
        except Exception:  # noqa: BLE001 — a timeout means it never agreed
            try:
                return self.http.get(url, headers=headers) or {}
            except Exception:  # noqa: BLE001
                return {}
