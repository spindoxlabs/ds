"""The onboarding seam — what ds owes the caller that admits people to a REC.

The onboarding service is **out of this repository**. What ds can assert about
the seam is therefore not "the service works" but something narrower and more
useful: *the eight scopes `services/keycloak/clients.yaml` grants
`svc-ds-onboarding` are sufficient for the calls that seam makes, and the routes
they reach take arguments that caller can actually hold.*

That is only an assertion if the flow authenticates **as that client**. Every
other flow here uses `svc-ds-e2e`, which holds a superset; run this seam under
that token and both defects it was written for disappear:

- `GET /owners/resolve` answered **403** to a client whose realm entry grants
  `identity-registry.organizations.read` with the annotation *"resolve the bound
  community's organisation at boot"*. The service fell back to
  `GET /admin/owners/{alias}`, which matches on `Owner.id` and 404s on an alias
  — read on that side as *no such organisation*.
- `POST /admin/disclosure` required a `dataset_id`. The caller's POD-list export
  is scoped to one **offer**, and `D-13` keeps dataset keys out of the public
  projection deliberately, so it had no way to name one. `connector.disclosure.record`
  was granted to this client by name, for a route it could not call.

The flow walks the seam in order: resolve the organisation, read the offers a
wizard renders, provision the person's decision, record the handover to the DSO,
and check the record is what `L-2` asks for. It also asserts the **control** —
that the permission fix did not quietly widen — because a fix that admits the
caller by granting it the participant registry would pass every other step here.

Out of scope, deliberately: everything downstream of the handover. The DSO
ingesting, republishing and third parties consuming is a different problem with a
different controller (`plans/onboarding-seam.md`, "Out of scope").

Needs connector, identity-registry, provenance and Keycloak. No EDC.
"""
from __future__ import annotations

import logging
import urllib.parse
import uuid
from typing import Any

from ds_e2e.consent import legal_basis
from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

SHA256_HEX_LEN = 64


class OnboardingSeamFlow(BaseFlow):
    name = "onboarding-seam"
    description = (
        "The seam an external onboarding service calls: owner resolution by "
        "alias, offer-scoped consent provisioning and offer-scoped disclosure, "
        "under that service's own client and its own scopes"
    )
    # `L-2` — one `DataDisclosed` per resolved dataset, each carrying that
    # dataset's own recomputable hash. `L-4` — the same export replayed under one
    # event id records nothing new, which an offer expanding to several datasets
    # is the easiest way to get wrong. `D-13` — the offer projection a wizard
    # renders carries a count and no dataset keys, which is *why* the disclosure
    # route had to take an offer.
    rules = ("L-2", "L-4", "D-13")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._provisioned = False

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        for name, url in (
            ("connector", s.connector_url),
            ("identity-registry", s.identity_registry_url),
            ("provenance", s.provenance_url),
        ):
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step("health", f"{name} unreachable: {exc}")
                return result
        result.pass_step("health", "connector, identity-registry and provenance reachable")

        # The identity under test. Everything below runs on this token.
        try:
            onboarding = self.http.bearer_headers_for(
                s.onboarding_client_id, s.onboarding_client_secret
            )
        except Exception as exc:
            result.fail_step(
                "onboarding client",
                f"could not authenticate as '{s.onboarding_client_id}': {exc}. "
                "The realm must carry the client this seam is written for — "
                "borrowing the harness client would prove nothing.",
            )
            return result
        result.pass_step(
            "onboarding client",
            "authenticated as the onboarding service's own client",
            client_id=s.onboarding_client_id,
        )

        if not self._check_owner_resolution(result, onboarding):
            return result
        if not self._check_perimeter_held(result, onboarding):
            return result

        offer = self._check_public_offer_projection(result)
        if offer is None:
            return result

        if not self._provision_the_decision(result, onboarding, offer):
            return result

        if not self._read_the_audience(result, onboarding, offer):
            return result

        disclosures = self._record_the_handover(result, onboarding, offer)
        if disclosures is None:
            return result

        self._check_hashes_recompute(result, disclosures)
        self._check_replay_records_nothing_new(result, onboarding, offer)
        return result

    # ── Phase 1: the organisation, by the name the caller holds ──────────────

    def _check_owner_resolution(self, result: FlowResult, headers: dict[str, str]) -> bool:
        s = self.settings
        ir = s.identity_registry_url

        for label, name in (("id", s.owning_org), ("alias", s.owning_org_alias)):
            status, payload = self.http.raw(
                "GET",
                f"{ir}/owners/resolve?alias={urllib.parse.quote(name)}",
                headers=headers,
            )
            if status != 200 or not isinstance(payload, dict):
                result.fail_step(
                    "resolve owner",
                    f"resolving the organisation by {label} answered {status}. "
                    "403 is the guard refusing the client its realm entry names; "
                    "404 by alias is the id-only route answering.",
                    queried=name,
                    status_code=status,
                    response=payload,
                )
                return False
            if payload.get("id") != s.owning_org:
                result.fail_step(
                    "resolve owner",
                    f"resolving by {label} returned a different organisation",
                    queried=name,
                    resolved=payload.get("id"),
                )
                return False

        result.pass_step(
            "resolve owner",
            "the organisation resolves by id and by alias to one canonical owner",
            owner=s.owning_org,
            alias=s.owning_org_alias,
        )
        return True

    def _check_perimeter_held(self, result: FlowResult, headers: dict[str, str]) -> bool:
        """The control, and the reason this flow is not just a happy path.

        Admitting the caller by granting it `identity-registry.read` would pass
        every other step here and undo the split `P6` made deliberately: that
        scope also reaches the participant registry and the presentation queries,
        and a process that provisions people has no business in either.
        """
        ir = self.settings.identity_registry_url
        reached = []
        for path in (
            "/admin/participants",
            "/admin/participants/check?did=did:web:x.example.test&scope=read",
            "/admin/memberships",
            "/admin/credentials",
        ):
            status, _ = self.http.raw("GET", f"{ir}{path}", headers=headers)
            if status != 403:
                reached.append(f"GET {path} → {status}")

        if reached:
            result.fail_step(
                "perimeter held",
                "the onboarding client reached a route outside its grant — "
                "resolving its own organisation is not authority to enumerate "
                "the dataspace",
                reached=reached,
            )
            return False
        result.pass_step(
            "perimeter held",
            "the participant, membership and credential registries stay closed to "
            "the same token",
            probes=4,
        )
        return True

    # ── What a wizard renders, before anyone has an identity ─────────────────

    def _check_public_offer_projection(self, result: FlowResult) -> dict[str, Any] | None:
        """`D-13` — and the reason the disclosure route had to take an offer.

        This is the surface the onboarding wizard reads, unauthenticated by
        design. It carries `dataset_count` and no dataset keys: which datasets
        back an offer is operator detail the person was never shown. So the
        caller genuinely cannot name a dataset, and a route that demanded one was
        asking it for something it is deliberately not told.
        """
        s = self.settings
        # A bare list, and unauthenticated — no headers, deliberately: this is
        # the surface a wizard reads before anyone has an identity, and asserting
        # it with a token would not test the property that makes `D-13` matter.
        status, payload = self.http.raw("GET", f"{s.connector_url}/ns/sharing-offers")
        if status != 200 or not isinstance(payload, list):
            result.fail_step(
                "public offer projection",
                "the offer projection a wizard renders is not being served",
                status_code=status,
            )
            return None

        offers = [o for o in payload if isinstance(o, dict)]
        leaked = [o.get("id") for o in offers if "datasets" in o]
        if leaked:
            result.fail_step(
                "public offer projection",
                "the public projection leaks dataset keys (D-13)",
                offers=leaked,
            )
            return None

        offer = next((o for o in offers if o.get("id") == s.sharing_offer_id), None)
        if offer is None:
            result.fail_step(
                "public offer projection",
                f"offer '{s.sharing_offer_id}' is not published",
                published=[o.get("id") for o in offers],
            )
            return None
        if not isinstance(offer.get("dataset_count"), int) or offer["dataset_count"] < 1:
            result.fail_step(
                "public offer projection",
                "the offer publishes no usable dataset_count, so there is nothing "
                "to check the disclosure expansion against",
                offer=offer.get("id"),
                dataset_count=offer.get("dataset_count"),
            )
            return None

        result.pass_step(
            "public offer projection",
            "the offer publishes a dataset count and no dataset keys",
            offer=offer["id"],
            dataset_count=offer["dataset_count"],
        )
        return offer

    # ── The person's decision, provisioned by the service ────────────────────

    def _provision_the_decision(
        self, result: FlowResult, headers: dict[str, str], offer: dict[str, Any]
    ) -> bool:
        s = self.settings
        status, payload = self.http.raw(
            "POST",
            f"{s.connector_url}/consent/admin/shares",
            body={
                "subject_id": s.data_subject_id,
                "offer_id": offer["id"],
                "enabled": True,
                "legal_basis": legal_basis(
                    f"onboarding-seam-{uuid.uuid4().hex[:12]}",
                    source="ds-e2e-onboarding-seam",
                ),
            },
            headers=headers,
        )
        if status != 200 or not isinstance(payload, list) or not payload:
            result.fail_step(
                "provision the decision",
                "the onboarding client could not record the subject's decision — "
                "`connector.consent.provision` is granted to it by name",
                status_code=status,
                response=payload,
            )
            return False

        self._provisioned = True
        # One consent row per dataset the offer resolves to, which is the same
        # expansion the disclosure route now performs. If these two disagree the
        # seam has two answers to the same question.
        if len(payload) != offer["dataset_count"]:
            result.fail_step(
                "provision the decision",
                "the offer expanded into a different number of consent rows than "
                "the published dataset_count — the write side and the public "
                "projection disagree about what the offer reaches",
                rows=len(payload),
                dataset_count=offer["dataset_count"],
            )
            return False

        result.pass_step(
            "provision the decision",
            "the offer expanded into one consent row per dataset it reaches",
            subject=s.data_subject_id,
            rows=len(payload),
        )
        return True

    # ── The read back, before the export ─────────────────────────────────────

    def _read_the_audience(
        self, result: FlowResult, headers: dict[str, str], offer: dict[str, Any]
    ) -> bool:
        """Who consents to this offer — the fact the export is built on.

        Provisioning and disclosing were reachable before this route existed and
        the read between them was not, so an export ran against a consent state
        the exporting service could not see. This step asserts the seam in the
        order the production caller uses it: provision, read the audience, then
        record the handover.

        Run on the **onboarding client's own token**, like every step in this
        flow. Borrowing the harness client would prove the route works and not
        that the service that needs it can reach it, which is the only question
        a new scope raises.
        """
        s = self.settings
        params = urllib.parse.urlencode(
            {"offer_id": offer["id"], "consumer_id": s.consumer_did}
        )
        status, payload = self.http.raw(
            "GET",
            f"{s.connector_url}/consent/admin/shares?{params}",
            headers=headers,
        )
        if status != 200 or not isinstance(payload, dict):
            result.fail_step(
                "read the audience",
                "the audience read was refused. A 403 here is the realm missing "
                "`connector.consent.audience` on the onboarding client — the "
                "scope is deliberately not `connector.consent.provision`, so "
                "holding the write grant does not carry it.",
                status_code=status,
                response=payload,
            )
            return False

        datasets = payload.get("datasets")
        if not isinstance(datasets, list) or len(datasets) != offer["dataset_count"]:
            result.fail_step(
                "read the audience",
                "the audience reports a different number of datasets than the "
                "published projection — a caller reading the first set would "
                "export against one dataset's consent and draw from another.",
                sets=len(datasets) if isinstance(datasets, list) else None,
                dataset_count=offer["dataset_count"],
            )
            return False

        if payload.get("purpose") != [s.consented_purpose]:
            result.fail_step(
                "read the audience",
                "the purpose was not stamped from the offer. The caller supplies "
                "none precisely so it cannot under-specify its way to an empty "
                "answer, so a mismatch means the route answered a different "
                "question than the one the offer asks.",
                purpose=payload.get("purpose"),
                expected=[s.consented_purpose],
            )
            return False

        if not all(s.data_subject_id in d.get("subject_ids", []) for d in datasets):
            result.fail_step(
                "read the audience",
                "the subject provisioned one step ago is absent from the "
                "audience, so the export would omit someone who consented.",
                subject=s.data_subject_id,
                datasets=datasets,
            )
            return False

        # The parameter that must not default. Omitting it would leave the
        # connector reading wildcard rows alone, so every per-party opt-out
        # would be invisible and the answer would name people who had withdrawn.
        refused, _ = self.http.raw(
            "GET",
            f"{s.connector_url}/consent/admin/shares"
            f"?offer_id={urllib.parse.quote(offer['id'])}",
            headers=headers,
        )
        if refused != 422:
            result.fail_step(
                "read the audience",
                "the route answered without a consumer instead of refusing. A "
                "default consumer sees only the standing wildcard, so it "
                "discloses to recipients a subject has specifically withdrawn "
                "from — the defect this route exists to prevent.",
                status_code=refused,
            )
            return False

        result.pass_step(
            "read the audience",
            "the offer's consenting subjects came back per dataset, purpose "
            "stamped from the offer, and a call without a consumer was refused",
            subject=s.data_subject_id,
            sets=len(datasets),
        )
        return True

    # ── The handover, recorded by offer ──────────────────────────────────────

    def _record_the_handover(
        self, result: FlowResult, headers: dict[str, str], offer: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """`L-2` on the argument the caller actually has.

        The POD-list export is scoped to one offer. Posting it by offer must emit
        one `DataDisclosed` per dataset the offer resolves to — expanded here
        rather than in the caller, because `datasets_for_offer` returns a list and
        a caller reading its first element is correct until a second dataset
        declares the same offer and then silently wrong.
        """
        s = self.settings
        before = self._count_events("DataDisclosed")

        status, payload = self.http.raw(
            "POST",
            f"{s.connector_url}/admin/disclosure",
            body={
                "offer_id": offer["id"],
                "recipient_ref": "e2e-local-dso",
                "purpose": [s.consented_purpose],
                "columns": ["pod_code", "consumption"],
                "subject_count": 1,
                "source_ref": "e2e-onboarding-seam-pod-list",
                "agreement_ref": "e2e-dpa-ref",
                "event_id": self._event_id,
            },
            headers=headers,
        )
        if status != 200 or not isinstance(payload, dict):
            result.fail_step(
                "record the handover",
                "the disclosure was refused. 422 on a valid offer is the route "
                "still demanding a dataset the caller cannot name.",
                status_code=status,
                response=payload,
            )
            return None

        disclosures = payload.get("disclosures")
        if not isinstance(disclosures, list) or not disclosures:
            result.fail_step(
                "record the handover",
                "the response carries no per-dataset record, so nothing says "
                "which datasets the handover covered",
                response=payload,
            )
            return None

        if "dataset_id" in payload or "consent_snapshot_hash" in payload:
            result.fail_step(
                "record the handover",
                "an offer-scoped response flattened to a single dataset. A caller "
                "reading those keys would be reading one of several, and would be "
                "correct only until a second dataset declared the offer.",
                response_keys=sorted(payload),
            )
            return None

        if len(disclosures) != offer["dataset_count"]:
            result.fail_step(
                "record the handover",
                "the disclosure expanded to a different number of datasets than "
                "the offer publishes — the route and the offer-to-dataset mapping "
                "have drifted",
                disclosed=len(disclosures),
                dataset_count=offer["dataset_count"],
            )
            return None

        bad = [
            d
            for d in disclosures
            if len(str(d.get("consent_snapshot_hash", ""))) != SHA256_HEX_LEN
        ]
        if bad:
            result.fail_step(
                "record the handover",
                "a disclosure carries no recomputable consent snapshot (L-2)",
                datasets=[d.get("dataset_id") for d in bad],
            )
            return None

        after = self._count_events("DataDisclosed")
        if after - before != len(disclosures):
            result.fail_step(
                "record the handover",
                "the events recorded do not match the datasets reported. One "
                "event id reused across several datasets is deduplicated by the "
                "provenance service, which leaves a 200 saying more than the "
                "graph holds.",
                before=before,
                after=after,
                disclosed=len(disclosures),
            )
            return None

        result.pass_step(
            "record the handover",
            "one DataDisclosed per dataset the offer reaches, each with its own "
            "consent snapshot",
            offer=offer["id"],
            datasets=[d.get("dataset_id") for d in disclosures],
            events_recorded=after - before,
        )
        return disclosures

    def _check_hashes_recompute(self, result: FlowResult, disclosures: list[dict[str, Any]]) -> None:
        """`L-2` asks the hash to be *recomputable*, not merely present.

        Recomputed through `POST /admin/ingestion`, which fingerprints the same
        consent state with the same function — so agreement between the two is
        the property, and a per-call value would fail it. That route belongs to a
        different caller and the harness token is what holds its scope; this leg
        is the verification, not part of the seam.
        """
        s = self.settings
        try:
            svc = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("snapshot recomputes", f"no harness token: {exc}")
            return

        mismatched = []
        for d in disclosures:
            status, payload = self.http.raw(
                "POST",
                f"{s.connector_url}/admin/ingestion",
                body={
                    "dataset_id": d["dataset_id"],
                    "source_ref": "e2e-onboarding-seam-recheck",
                    "record_count": 1,
                    "event_id": f"e2e-seam-recheck-{uuid.uuid4().hex[:12]}",
                },
                headers=svc,
            )
            if status != 200 or not isinstance(payload, dict):
                mismatched.append(f"{d['dataset_id']}: recompute answered {status}")
                continue
            if payload.get("consent_snapshot_hash") != d["consent_snapshot_hash"]:
                mismatched.append(
                    f"{d['dataset_id']}: disclosure and ingestion disagree on the "
                    "consent state that authorised them"
                )

        if mismatched:
            result.fail_step(
                "snapshot recomputes",
                "a consent snapshot hash could not be reproduced over the same "
                "consent state (L-2)",
                mismatched=mismatched,
            )
            return
        result.pass_step(
            "snapshot recomputes",
            "every disclosed dataset's hash reproduces over the same consent state",
            datasets=len(disclosures),
        )

    def _check_replay_records_nothing_new(
        self, result: FlowResult, headers: dict[str, str], offer: dict[str, Any]
    ) -> None:
        """`L-4` — and the failure mode is specific to the offer form.

        The provenance service dedupes on `event_id`. An offer expanding to N
        datasets under one caller-supplied id must produce N distinct keys, or the
        first replay would look idempotent for the wrong reason: it would record
        one event the first time too.
        """
        s = self.settings
        before = self._count_events("DataDisclosed")
        status, _ = self.http.raw(
            "POST",
            f"{s.connector_url}/admin/disclosure",
            body={
                "offer_id": offer["id"],
                "recipient_ref": "e2e-local-dso",
                "purpose": [s.consented_purpose],
                "columns": ["pod_code", "consumption"],
                "subject_count": 1,
                "source_ref": "e2e-onboarding-seam-pod-list",
                "agreement_ref": "e2e-dpa-ref",
                "event_id": self._event_id,  # the same id as before
            },
            headers=headers,
        )
        after = self._count_events("DataDisclosed")
        if status != 200:
            result.fail_step(
                "export replay is a no-op",
                "replaying the export was refused rather than deduplicated",
                status_code=status,
            )
            return
        if after != before:
            result.fail_step(
                "export replay is a no-op",
                "replaying the same export under the same event id recorded the "
                "handover a second time (L-4)",
                before=before,
                after=after,
            )
            return
        result.pass_step(
            "export replay is a no-op",
            "the same export replayed under one event id records nothing new, and "
            "its datasets stayed distinct",
            data_disclosed_events=after,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @property
    def _event_id(self) -> str:
        """One id per run, stable across the two posts that must deduplicate.

        Generated once and cached so `execute` and the replay leg agree, and
        different per run so a re-run is not silently deduplicated against the
        previous one's events.
        """
        if not hasattr(self, "_event_id_value"):
            self._event_id_value = f"e2e-seam-export-{uuid.uuid4().hex[:12]}"
        return self._event_id_value

    def _count_events(self, event_type: str) -> int:
        s = self.settings
        query = urllib.parse.urlencode({"event_type": event_type, "limit": 500})
        try:
            payload = (
                self.http.get(
                    f"{s.provenance_url}/prov/events?{query}",
                    headers=self.http.bearer_headers(),
                )
                or {}
            )
        except Exception as exc:  # noqa: BLE001 — reported as a step, not raised
            log.warning("could not read the provenance event log: %s", exc)
            return -1
        graph = payload.get("@graph") or []
        return len([g for g in graph if isinstance(g, dict)])

    def cleanup(self) -> None:
        """Withdraw the standing decision this flow provisioned.

        Withdrawal carries no evidence record and must not: a person may always
        stop, and supplying proof to stop would hide a regression in that rule.
        """
        if not self._provisioned:
            return
        s = self.settings
        try:
            self.http.raw(
                "POST",
                f"{s.connector_url}/consent/admin/shares",
                body={
                    "subject_id": s.data_subject_id,
                    "offer_id": s.sharing_offer_id,
                    "enabled": False,
                },
                headers=self.http.bearer_headers_for(
                    s.onboarding_client_id, s.onboarding_client_secret
                ),
            )
        except Exception as exc:  # noqa: BLE001 — cleanup must not mask the result
            log.warning("could not withdraw the provisioned share: %s", exc)
