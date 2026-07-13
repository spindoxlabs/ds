"""GovernanceMapper — converts GovernanceRuleV2 to ODRL and EDC payloads."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import GovernanceRuleV2, OdrlProfile

# No module-level tag→purpose mapping — deployers configure this via
# OdrlProfile.tag_to_purpose so the platform stays domain-neutral.

# ── Permitted actions by access_level ─────────────────────────────────────────
# "{profile}" is replaced with the profile query-action IRI at runtime.

_LEVEL_ACTION_KEYS: dict[str, list[str]] = {
    "open":       ["{query}", "odrl:aggregate", "odrl:transfer"],
    "internal":   ["{query}", "odrl:aggregate"],
    "restricted": ["{query}"],
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

    def __init__(
        self,
        participant_id: str,
        base_url: str,
        profile: OdrlProfile | None = None,
        owner_did_resolver: Callable[[str], str | None] | None = None,
    ):
        self.participant_id = participant_id
        self.base_url = base_url.rstrip("/")
        self.profile = profile or OdrlProfile()
        self._resolve_owner_did = owner_did_resolver

    def _resolve_actions(self, keys: list[str]) -> list[str]:
        """Replace ``{query}`` placeholder with profile query-action IRI."""
        query_iri = self.profile.term(self.profile.query_action)
        return [query_iri if k == "{query}" else k for k in keys]

    def _resolve_assigner(self, rule: GovernanceRuleV2) -> str:
        """Resolve the ODRL assigner DID from rule ownership or fall back to participant DID."""
        if self._resolve_owner_did and rule.ownership:
            for owner in rule.ownership:
                did = self._resolve_owner_did(owner.name)
                if did:
                    return did
        return f"did:web:{self.participant_id}.dataspaces.localhost"

    # ── ODRL ──────────────────────────────────────────────────────────────────

    def to_odrl_offer(self, dataset_key: str, rule: GovernanceRuleV2) -> dict[str, Any]:
        """Return a full ODRL Offer dict for the given dataset."""
        p = self.profile
        policy = rule.policy
        access_level = rule.access_level or "internal"

        action_keys = policy.permitted_actions or _LEVEL_ACTION_KEYS.get(access_level, ["{query}"])
        permitted = self._resolve_actions(action_keys)
        prohibited = policy.prohibited_actions or _CLASS_PROHIBITIONS.get(rule.classification or "green", [])
        purposes = policy.purpose or self._derive_purposes(rule.tags)

        offer_id = f"urn:offer:{self.participant_id}:{dataset_key.replace('.', ':')}"

        permissions = [
            self._build_permission(action, access_level, rule.access_requirements, purposes, policy, rule)
            for action in permitted
        ]

        prohibitions = [
            {"odrl:action": {"@id": action}}
            for action in prohibited
        ]

        obligations = self._build_obligations(rule)

        context: dict[str, Any] = {
            "odrl": "http://www.w3.org/ns/odrl/2/",
            p.prefix: p.namespace,
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        }
        if p.profile_iri:
            context["odrl:profile"] = p.profile_iri

        return {
            "@context": context,
            "@type": "odrl:Offer",
            "@id": offer_id,
            "odrl:assigner": {"@id": self._resolve_assigner(rule)},
            "odrl:permission": permissions,
            "odrl:prohibition": prohibitions,
            "odrl:obligation": obligations,
        }

    def _build_permission(
        self,
        action: str,
        access_level: str,
        access_requirements: str | None,
        purposes: list[str],
        policy: Any,
        rule: GovernanceRuleV2,
    ) -> dict[str, Any]:
        p = self.profile
        constraints: list[dict[str, Any]] = []

        # Membership constraint — driven by access_requirements when set, else by access_level
        reqs = access_requirements or "all"
        needs_membership = reqs in ("partner", "contract") or access_level in ("internal", "restricted")
        if needs_membership:
            constraints.append({
                "odrl:leftOperand": {"@id": p.term(p.membership_operand)},
                "odrl:operator": {"@id": "odrl:eq"},
                "odrl:rightOperand": {"@value": policy.audience.required_scope, "@type": "xsd:string"},
            })

        # Contract constraint — access_requirements = "contract"
        if reqs == "contract":
            constraints.append({
                "odrl:leftOperand": {"@id": "odrl:industry"},
                "odrl:operator": {"@id": "odrl:eq"},
                "odrl:rightOperand": {"@value": "contract-agreed", "@type": "xsd:string"},
            })

        # Purpose constraint
        for purpose in purposes:
            constraints.append({
                "odrl:leftOperand": {"@id": "odrl:purpose"},
                "odrl:operator": {"@id": "odrl:isA"},
                "odrl:rightOperand": {"@id": purpose},
            })

        # Consent constraint
        consent = policy.consent
        needs_consent = consent.required or bool(rule.row_filters) or bool(rule.user_filter_column)
        if needs_consent:
            constraints.append({
                "odrl:leftOperand": {"@id": p.term(p.consent_operand)},
                "odrl:operator": {"@id": "odrl:eq"},
                "odrl:rightOperand": {"@value": "active", "@type": "xsd:string"},
            })

        perm: dict[str, Any] = {
            "odrl:action": {"@id": action},
        }
        if constraints:
            perm["odrl:constraint"] = constraints

        # Consent pre-duty
        if needs_consent:
            perm["odrl:duty"] = [{
                "odrl:action": {"@id": "odrl:obtainConsent"},
            }]

        return perm

    def _build_obligations(self, rule: GovernanceRuleV2) -> list[dict[str, Any]]:
        obligations: list[dict[str, Any]] = []
        ob = rule.policy.obligations

        delete_days = ob.delete_after_days or rule.retention_days
        if delete_days:
            obligations.append({
                "odrl:action": [{"rdf:value": {"@id": "odrl:delete"},
                    "odrl:refinement": [{
                        "odrl:leftOperand": {"@id": "odrl:delayPeriod"},
                        "odrl:operator": {"@id": "odrl:lteq"},
                        "odrl:rightOperand": {
                            "@value": f"P{delete_days}D",
                            "@type": "xsd:duration",
                        },
                    }],
                }],
            })

        if ob.attribution and rule.attribution:
            obligations.append({
                "odrl:action": {"@id": "odrl:attributeTo"},
                "odrl:attributeTo": {"@id": self._resolve_assigner(rule)},
                "odrl:target": rule.attribution,
            })

        return obligations

    def _derive_purposes(self, tags: list[str]) -> list[str]:
        tag_map = self.profile.tag_to_purpose
        seen: set[str] = set()
        purposes: list[str] = []
        for tag in tags:
            slug = tag_map.get(tag)
            if slug and slug not in seen:
                purposes.append(self.profile.purpose_iri(slug))
                seen.add(slug)
        return purposes

    # ── EDC Asset ─────────────────────────────────────────────────────────────

    def to_asset_create(self, dataset_key: str, rule: GovernanceRuleV2) -> dict[str, Any]:
        ds = rule.dataspace
        asset_id = ds.asset.id or f"{self.base_url}/datasets/{dataset_key.replace('.', '/')}"
        medallion = ds.medallion or self._infer_medallion(dataset_key)
        pfx = self.profile.prefix

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
                f"{pfx}:medallion": medallion,
                f"{pfx}:classification": rule.classification,
                f"{pfx}:sourceSystem": rule.source_system,
                f"{pfx}:tags": ",".join(rule.tags),
                f"{pfx}:userFilterColumn": (
                    rule.row_filters[0].args.column if rule.row_filters
                    else rule.user_filter_column
                ),
                f"{pfx}:rowFilters": [
                    {"handler": f.handler, "column": f.args.column}
                    for f in rule.row_filters
                ] or None,
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
