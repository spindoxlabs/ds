"""GovernanceMapper — converts GovernanceRuleV2 to ODRL and EDC payloads."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import GovernanceRuleV2

# ── Purpose auto-derivation from tags ─────────────────────────────────────────

_TAG_TO_PURPOSE: dict[str, str] = {
    "rec":      "ds:purpose:EnergyBalancing",
    "meters":   "ds:purpose:EnergyBalancing",
    "grid":     "ds:purpose:GridMonitoring",
    "tourism":  "ds:purpose:UrbanPlanning",
    "mobility": "ds:purpose:UrbanPlanning",
}

# ── Permitted actions by access_level ─────────────────────────────────────────

_LEVEL_ACTIONS: dict[str, list[str]] = {
    "open":       ["ds:query", "odrl:aggregate", "odrl:transfer"],
    "internal":   ["ds:query", "odrl:aggregate"],
    "restricted": ["ds:query"],
    "secret":     [],
}

# ── Auto prohibitions by classification ───────────────────────────────────────

_CLASS_PROHIBITIONS: dict[str, list[str]] = {
    "pii":    ["odrl:transfer", "odrl:derive", "odrl:distribute", "odrl:sublicense"],
    "red":    ["odrl:transfer", "odrl:sublicense"],
    "yellow": ["odrl:sublicense"],
    "green":  [],
}


class GovernanceMapper:
    """Converts a GovernanceRuleV2 into ODRL and EDC Management API payloads.

    Usage::

        mapper = GovernanceMapper(participant_id="provider",
                                  base_url="https://provider.dataspaces.localhost")
        odrl = mapper.to_odrl_offer("datasets.gold.meters_15m", rule)
        asset = mapper.to_asset_create("datasets.gold.meters_15m", rule)
    """

    DS_NAMESPACE = "https://dataspaces.localhost/ns/energy#"

    def __init__(self, participant_id: str, base_url: str):
        self.participant_id = participant_id
        self.base_url = base_url.rstrip("/")

    # ── ODRL ──────────────────────────────────────────────────────────────────

    def to_odrl_offer(self, dataset_key: str, rule: GovernanceRuleV2) -> dict[str, Any]:
        """Return a full ODRL Offer dict for the given dataset."""
        policy = rule.policy
        access_level = rule.access_level or "internal"

        permitted = policy.permitted_actions or _LEVEL_ACTIONS.get(access_level, ["ds:query"])
        prohibited = policy.prohibited_actions or _CLASS_PROHIBITIONS.get(rule.classification or "green", [])
        purposes = policy.purpose or self._derive_purposes(rule.tags)

        offer_id = f"urn:offer:{self.participant_id}:{dataset_key.replace('.', ':')}"

        permissions = [
            self._build_permission(action, access_level, purposes, policy, rule)
            for action in permitted
        ]

        prohibitions = [
            {"odrl:action": {"@id": action}}
            for action in prohibited
        ]

        obligations = self._build_obligations(rule)

        return {
            "@context": {
                "odrl": "http://www.w3.org/ns/odrl/2/",
                "ds": self.DS_NAMESPACE,
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
            "@type": "odrl:Offer",
            "@id": offer_id,
            "odrl:assigner": {"@id": f"did:web:{self.participant_id}.dataspaces.localhost"},
            "odrl:permission": permissions,
            "odrl:prohibition": prohibitions,
            "odrl:obligation": obligations,
        }

    def _build_permission(
        self,
        action: str,
        access_level: str,
        purposes: list[str],
        policy: Any,
        rule: GovernanceRuleV2,
    ) -> dict[str, Any]:
        constraints: list[dict] = []

        # Scope constraint for non-open datasets
        if access_level in ("internal", "restricted"):
            constraints.append({
                "odrl:leftOperand": {"@id": "ds:accessScope"},
                "odrl:operator": {"@id": "odrl:eq"},
                "odrl:rightOperand": policy.audience.required_scope,
            })

        # Purpose constraint
        for purpose in purposes:
            constraints.append({
                "odrl:leftOperand": {"@id": "odrl:purpose"},
                "odrl:operator": {"@id": "odrl:isA"},
                "odrl:rightOperand": {"@id": purpose},
            })

        # Consent constraint (when user_filter_column triggers consent requirement)
        consent = policy.consent
        if consent.required or rule.user_filter_column:
            constraints.append({
                "odrl:leftOperand": {"@id": "ds:consentStatus"},
                "odrl:operator": {"@id": "odrl:eq"},
                "odrl:rightOperand": "active",
            })

        perm: dict[str, Any] = {
            "odrl:action": {"@id": action},
        }
        if constraints:
            perm["odrl:constraint"] = constraints

        # Consent pre-duty
        if consent.required or rule.user_filter_column:
            perm["odrl:duty"] = [{
                "odrl:action": {"@id": "odrl:obtainConsent"},
                "odrl:consentingParty": {"@id": "ds:role:DataSubject"},
            }]

        return perm

    def _build_obligations(self, rule: GovernanceRuleV2) -> list[dict]:
        obligations: list[dict] = []
        ob = rule.policy.obligations

        delete_days = ob.delete_after_days or rule.retention_days
        if delete_days:
            obligations.append({
                "odrl:action": {"@id": "odrl:delete"},
                "odrl:constraint": [{
                    "odrl:leftOperand": "odrl:dateTime",
                    "odrl:operator": {"@id": "odrl:lt"},
                    "odrl:rightOperand": {
                        "@type": "xsd:duration",
                        "@value": f"P{delete_days}D",
                    },
                }],
            })

        if ob.attribution and rule.attribution:
            obligations.append({
                "odrl:action": {"@id": "odrl:attribute"},
                "odrl:attributedParty": {
                    "@id": f"did:web:{self.participant_id}.dataspaces.localhost"
                },
                "odrl:attributeUrl": rule.attribution,
            })

        return obligations

    @staticmethod
    def _derive_purposes(tags: list[str]) -> list[str]:
        seen: set[str] = set()
        purposes: list[str] = []
        for tag in tags:
            purpose = _TAG_TO_PURPOSE.get(tag)
            if purpose and purpose not in seen:
                purposes.append(purpose)
                seen.add(purpose)
        return purposes

    # ── EDC Asset ─────────────────────────────────────────────────────────────

    def to_asset_create(self, dataset_key: str, rule: GovernanceRuleV2) -> dict[str, Any]:
        ds = rule.dataspace
        asset_id = ds.asset.id or f"{self.base_url}/datasets/{dataset_key.replace('.', '/')}"
        medallion = ds.medallion or self._infer_medallion(dataset_key)

        data_address: dict[str, Any] = {
            "type": ds.data_address.type,
            "baseUrl": ds.data_address.base_url,
            "proxyPath": str(ds.data_address.proxy_path).lower(),
            "proxyQueryParams": str(ds.data_address.proxy_query_params).lower(),
        }
        for k, v in ds.data_address.query_params.items():
            data_address[f"queryParam:{k}"] = v

        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "Asset",
            "@id": asset_id,
            "properties": {
                "name": rule.title or dataset_key,
                "description": rule.description or "",
                "contenttype": ds.asset.content_type,
                "ds:medallion": medallion,
                "ds:classification": rule.classification,
                "ds:sourceSystem": rule.source_system,
                "ds:tags": ",".join(rule.tags),
                "ds:userFilterColumn": rule.user_filter_column,
            },
            "dataAddress": data_address,
        }

    # ── EDC Policy Definition ─────────────────────────────────────────────────

    def to_policy_create(self, dataset_key: str, rule: GovernanceRuleV2) -> dict[str, Any]:
        policy_id = (
            rule.dataspace.contract.access_policy_id
            or f"{dataset_key.replace('.', '-')}-policy"
        )
        odrl_offer = self.to_odrl_offer(dataset_key, rule)
        # EDC expects a Set (not an Offer) for PolicyDefinition
        odrl_set = {**odrl_offer, "@type": "odrl:Set"}
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "PolicyDefinition",
            "@id": policy_id,
            "policy": odrl_set,
        }

    # ── EDC Contract Definition ───────────────────────────────────────────────

    def to_contract_definition(
        self, dataset_key: str, rule: GovernanceRuleV2, policy_id: str, asset_id: str
    ) -> dict[str, Any]:
        ds = rule.dataspace
        contract_id = ds.contract.access_policy_id or f"{dataset_key.replace('.', '-')}-contract"
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "ContractDefinition",
            "@id": contract_id,
            "accessPolicyId": ds.contract.access_policy_id or policy_id,
            "contractPolicyId": ds.contract.contract_policy_id or policy_id,
            "assetsSelector": [{
                "@type": "CriterionDto",
                "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                "operator": "=",
                "operandRight": asset_id,
            }],
        }

    @staticmethod
    def _infer_medallion(dataset_key: str) -> str:
        for level in ("gold", "silver", "bronze", "raw", "staging"):
            if level in dataset_key:
                return level
        return "unknown"
