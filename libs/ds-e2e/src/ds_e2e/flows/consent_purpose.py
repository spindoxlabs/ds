"""Consent vocabulary flow — the purpose chain end to end.

`smoke` proves the purpose is enforced on the data path. This flow proves the
chain that makes that enforcement mean something:

    consent text (versioned)
           declares
    purpose slug ─────────► ODRL profile taxonomy (/ns/policy, SKOS)
           groups                    dpv_mapping → DPV IRI + relation
    sharing offer ── resolves to ──► governance datasets
           consented as
    consent row (dataset + purpose + controller-role, all validated)
           compared at
    /internal/consent/check

Every step here would have passed silently before Block A: purposes were
free-form strings, dataset ids were unvalidated, and the check took no purpose
at all.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.http import HttpError
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

SKOS_MATCH_RELATIONS = {
    "exactMatch",
    "broadMatch",
    "closeMatch",
    "narrowMatch",
    "relatedMatch",
}


def _slug(iri: str) -> str:
    """Last path or prefix segment of a purpose IRI.

    Separator-agnostic on purpose: the profile's ``purpose_base`` is deployer
    configuration, and the flow should assert on the taxonomy, not on how a
    deployment happens to punctuate its IRIs.
    """
    return iri.replace(":", "/").rstrip("/").rsplit("/", 1)[-1]


class ConsentPurposeFlow(BaseFlow):
    name = "consent-purpose"
    description = (
        "Purpose taxonomy, sharing offers, validated consent writes and "
        "purpose-scoped enforcement"
    )

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        try:
            self.http.acquire_service_token()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result
        svc_headers = self.http.bearer_headers()

        # 1. The taxonomy is served as SKOS, with a local hierarchy.
        concepts = self._check_taxonomy(result)
        if concepts is None:
            return result

        # 2. Offers resolve against that taxonomy and expose codes only.
        offer = self._check_offers(result)
        if offer is None:
            return result

        # 3. The subject's credential, for the consent write path.
        try:
            subject_vc = self._resolve_user_vc(s.data_subject_email, svc_headers)
        except Exception as exc:
            result.fail_step("load credentials", str(exc))
            return result
        subject_headers = {
            "X-Subject-Id": s.data_subject_id,
            "X-User-VC": subject_vc,
        }

        # 4. Writes are validated against all three vocabularies.
        if not self._check_write_validation(result, subject_headers):
            return result

        # 5. Consent by offer, then the odrl:isA matrix at the check endpoint.
        if not self._check_enforcement(result, subject_headers, svc_headers, offer):
            return result

        return result

    # ── 1. Taxonomy ──────────────────────────────────────────────────────────

    def _check_taxonomy(self, result: FlowResult) -> dict[str, dict] | None:
        s = self.settings
        try:
            vocab = self.http.get(f"{s.connector_url}/ns/policy") or {}
        except Exception as exc:
            result.fail_step("purpose taxonomy", str(exc))
            return None

        concepts = {
            _slug(str(item.get("@id", ""))): item
            for item in vocab.get("@graph", [])
            if isinstance(item, dict) and item.get("@type") == "skos:Concept"
        }
        if s.consented_purpose not in concepts:
            result.fail_step(
                "purpose taxonomy",
                f"'{s.consented_purpose}' is not published in the ODRL profile",
                published=sorted(concepts),
            )
            return None

        # Every declared external mapping must use a real SKOS match property.
        # A wrong relation is a false interop claim that fails silently.
        for slug, concept in concepts.items():
            declared = [
                key.removeprefix("skos:")
                for key in concept
                if key.startswith("skos:") and key.removeprefix("skos:") in SKOS_MATCH_RELATIONS
            ]
            for relation in declared:
                target = concept.get(f"skos:{relation}") or {}
                iri = target.get("@id") if isinstance(target, dict) else target
                if not iri or "://" not in str(iri):
                    result.fail_step(
                        "purpose taxonomy",
                        f"'{slug}' declares {relation} without an absolute IRI",
                    )
                    return None

        broader = [c for c in concepts.values() if "skos:broader" in c]
        if not broader:
            result.fail_step(
                "purpose taxonomy",
                "no purpose declares skos:broader — odrl:isA has no hierarchy to follow",
            )
            return None

        result.pass_step(
            "purpose taxonomy",
            "SKOS purpose taxonomy served with a local hierarchy and DPV alignment",
            concepts=sorted(concepts),
            with_broader=len(broader),
        )
        return concepts

    # ── 2. Offers ────────────────────────────────────────────────────────────

    def _check_offers(self, result: FlowResult) -> dict[str, Any] | None:
        s = self.settings
        try:
            offers = self.http.get(f"{s.connector_url}/ns/sharing-offers") or []
        except Exception as exc:
            result.fail_step("sharing offers", str(exc))
            return None

        offer = next((o for o in offers if o.get("id") == s.sharing_offer_id), None)
        if offer is None:
            result.fail_step(
                "sharing offers",
                f"offer '{s.sharing_offer_id}' not published",
                available=[o.get("id") for o in offers],
            )
            return None

        # Dataset keys are operator detail the person was never shown.
        leaked = [o["id"] for o in offers if "datasets" in o]
        if leaked:
            result.fail_step(
                "sharing offers", "public projection leaks dataset keys", offers=leaked
            )
            return None

        # Every code a frontend renders must carry an English fallback, so an
        # untranslated locale degrades to readable English, never a raw slug.
        missing = [
            o["id"] for o in offers if not o.get("fallback_text_en", {}).get("purpose_label")
        ]
        if missing:
            result.fail_step(
                "sharing offers", "offers without an English fallback label", offers=missing
            )
            return None

        # Contract-based offers must be disclosed without a toggle.
        contract_offers = [o for o in offers if not o.get("requires_consent")]

        result.pass_step(
            "sharing offers",
            "offers served as codes with English fallbacks and no dataset keys",
            consent_based=[o["id"] for o in offers if o.get("requires_consent")],
            disclosed_only=[o["id"] for o in contract_offers],
            purpose=offer.get("purpose"),
            purpose_broader=offer.get("purpose_broader"),
        )
        return offer

    # ── 3. Write validation ──────────────────────────────────────────────────

    def _check_write_validation(
        self, result: FlowResult, subject_headers: dict[str, str]
    ) -> bool:
        s = self.settings
        cases = [
            (
                "unknown dataset",
                {"dataset_id": "datasets.silver.does_not_exist", "enabled": True},
            ),
            (
                "out-of-taxonomy purpose",
                {
                    "dataset_id": s.asset_id,
                    "enabled": True,
                    "purpose": ["WhateverWeFeelLike"],
                },
            ),
            ("unknown offer", {"offer_id": "no-such-offer", "enabled": True}),
        ]
        for label, body in cases:
            status, payload = self.http.post_raw(
                f"{s.connector_url}/consent/my/shares", body, headers=subject_headers
            )
            if status != 422:
                result.fail_step(
                    "consent write validation",
                    f"{label} was not rejected with 422",
                    status_code=status,
                    response=payload,
                )
                return False

        result.pass_step(
            "consent write validation",
            "unknown datasets, purposes and offers are rejected at the write path",
            cases=[label for label, _ in cases],
        )
        return True

    # ── 4./5. Enforcement ────────────────────────────────────────────────────

    def _check_enforcement(
        self,
        result: FlowResult,
        subject_headers: dict[str, str],
        svc_headers: dict[str, str],
        offer: dict[str, Any],
    ) -> bool:
        s = self.settings

        try:
            rows = self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {
                    "offer_id": s.sharing_offer_id,
                    "consumer_id": s.consumer_did,
                    "enabled": True,
                },
                headers=subject_headers,
            ) or []
        except HttpError as exc:
            result.fail_step("consent by offer", f"HTTP {exc.status}", response=exc.body)
            return False

        rows = rows if isinstance(rows, list) else [rows]
        if not rows:
            result.fail_step("consent by offer", "offer expanded to no rows")
            return False
        for row in rows:
            if row.get("purpose") != [s.consented_purpose]:
                result.fail_step(
                    "consent by offer", "row purpose does not match the offer", row=row
                )
                return False
            if row.get("controller") != offer["recipients"]["controller"]:
                result.fail_step(
                    "consent by offer", "row controller does not match the offer", row=row
                )
                return False
            if row.get("offer_id") != s.sharing_offer_id:
                result.fail_step("consent by offer", "row is not linked to the offer", row=row)
                return False

        result.pass_step(
            "consent by offer",
            "offer expanded into per-dataset rows stamped with purpose and controller",
            datasets=[r.get("dataset_id") for r in rows],
            controller=offer["recipients"]["controller"],
        )

        # The odrl:isA matrix, evaluated by the same endpoint the EDC extension
        # and the dataset-api PEP both call.
        broader = (offer.get("purpose_broader") or [None])[0]
        cases: list[tuple[str, str | None, bool, str]] = [
            (
                "consented purpose",
                s.consented_purpose,
                True,
                "the purpose the subject agreed to is allowed",
            ),
            (
                "sibling purpose",
                s.unconsented_purpose,
                False,
                "a different purpose under the same parent is denied",
            ),
            (
                "no purpose",
                None,
                False,
                "an undeclared purpose is never a wildcard for personal data",
            ),
        ]
        if broader:
            cases.append(
                (
                    "broader purpose",
                    broader,
                    False,
                    "the parent of the consented purpose is denied — that would widen consent",
                )
            )

        for label, purpose, expected, why in cases:
            params: dict[str, str] = {
                "dataset_id": s.asset_id,
                "consumer_id": s.consumer_did,
                "subject_id": s.data_subject_id,
            }
            if purpose:
                params["purpose"] = purpose
            url = f"{s.connector_url}/internal/consent/check?{urllib.parse.urlencode(params)}"
            try:
                body = self.http.get(url, headers=svc_headers) or {}
            except Exception as exc:
                result.fail_step("purpose matching", f"{label}: {exc}")
                return False
            if bool(body.get("consent_active")) != expected:
                result.fail_step(
                    "purpose matching",
                    f"{label}: expected consent_active={expected} ({why})",
                    purpose=purpose,
                    reason=body.get("reason"),
                )
                return False

        result.pass_step(
            "purpose matching",
            "odrl:isA matching follows the local broader chain only",
            allowed=[s.consented_purpose],
            denied=[c[1] for c in cases if not c[2]],
        )

        self._withdraw_share(subject_headers)
        return True

    # ── helpers ──────────────────────────────────────────────────────────────

    def _withdraw_share(self, subject_headers: dict[str, str]) -> None:
        """Withdraw the standing share this flow provisioned.

        A flow revokes what it writes. Leaving this one granted made the *next*
        flow's assertions wrong rather than this one's: a pending consent request
        neither grants nor blocks, so it falls through to whatever standing
        decision the subject already has (``resolve_decision``, §3.1) — and
        ``consent-request`` would then find its own undecided request reported as
        authorised, which looks like a consent bug and is really a leftover row.

        Best-effort: a failure here must not fail a flow whose assertions have
        all passed.
        """
        s = self.settings
        try:
            self.http.post(
                f"{s.connector_url}/consent/my/shares",
                {
                    "offer_id": s.sharing_offer_id,
                    "consumer_id": s.consumer_did,
                    "enabled": False,
                },
                headers=subject_headers,
            )
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask results
            log.warning("consent-purpose: could not withdraw its standing share: %s", exc)

    def _resolve_user_vc(self, email: str, headers: dict[str, str]) -> str:
        s = self.settings
        encoded_email = urllib.parse.quote(email, safe="")
        resp = self.http.get(
            f"{s.identity_registry_url}/users/resolve?email={encoded_email}",
            headers=headers,
        ) or {}
        vc_jws = resp.get("vc_jws") or ""
        if not vc_jws:
            raise RuntimeError(f"No VC found for user {email}")
        return vc_jws
