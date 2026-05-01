"""Governance YAML → EDC payload service."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ds.governance.models import GovernanceRuleV2
from ds.governance.resolver import GovernanceResolver

from ..schemas.edc import AssetCreate, ContractDefCreate, DataAddress, PolicyCreate


def _derive_odrl_set(
    access_level: str | None,
    retention_days: int | None,
    classification: str | None,
) -> dict[str, Any]:
    """Auto-derive an ODRL Set from access_level + classification."""
    level = access_level or "internal"

    constraints: list[dict[str, Any]] = []
    if level in ("internal", "restricted"):
        constraints.append({
            "odrl:leftOperand": "ds:accessScope",
            "odrl:operator": {"@id": "odrl:eq"},
            "odrl:rightOperand": "dataspaces.query",
        })
    if level == "restricted":
        constraints.append({
            "odrl:leftOperand": "ds:contractRequired",
            "odrl:operator": {"@id": "odrl:eq"},
            "odrl:rightOperand": "true",
        })

    prohibited: list[dict[str, Any]] = []
    cls_ = classification or "green"
    if cls_ in ("pii", "red"):
        prohibited.append({"odrl:action": "odrl:distribute"})
    if cls_ == "pii":
        prohibited.append({"odrl:action": "odrl:sublicense"})

    obligations: list[dict[str, Any]] = []
    if retention_days:
        obligations.append({
            "odrl:action": "odrl:delete",
            "odrl:constraint": [{
                "odrl:leftOperand": "odrl:dateTime",
                "odrl:operator": {"@id": "odrl:lteq"},
                "odrl:rightOperand": f"P{retention_days}D",
            }],
        })

    return {
        "@context": "http://www.w3.org/ns/odrl.jsonld",
        "@type": "Set",
        "odrl:permission": [{"odrl:action": "odrl:use", "odrl:constraint": constraints}],
        "odrl:prohibition": prohibited,
        "odrl:obligation": obligations,
    }


class ConnectorGovernanceMapper:
    """Translates GovernanceRuleV2 into EDC Management API Pydantic objects."""

    def __init__(self, participant_id: str, participant_base_url: str):
        self.participant_id = participant_id
        self.base_url = participant_base_url.rstrip("/")

    def to_asset_create(self, dataset_key: str, rule: GovernanceRuleV2) -> AssetCreate:
        ds = rule.dataspace
        asset_id = ds.asset.id or f"{self.base_url}/datasets/{dataset_key.replace('.', '/')}"
        medallion = ds.medallion or self._infer_medallion(dataset_key)

        extra: dict[str, str] = {}
        for k, v in ds.data_address.query_params.items():
            extra[f"queryParam:{k}"] = v

        return AssetCreate(
            id=asset_id,
            properties={
                "name": rule.title or dataset_key,
                "description": rule.description or "",
                "contenttype": ds.asset.content_type,
                "ds:medallion": medallion,
                "ds:classification": rule.classification or "",
                "ds:sourceSystem": rule.source_system or "",
                "ds:tags": ",".join(rule.tags),
                "ds:userFilterColumn": (
                    rule.row_filters[0].args.column if rule.row_filters
                    else rule.user_filter_column or ""
                ),
                "ds:rowFilters": [
                    {"handler": f.handler, "column": f.args.column}
                    for f in rule.row_filters
                ] or None,
            },
            data_address=DataAddress(
                type=ds.data_address.type,
                base_url=ds.data_address.base_url,
                proxy_path=str(ds.data_address.proxy_path).lower(),
                proxy_query_params=str(ds.data_address.proxy_query_params).lower(),
                extra=extra,
            ),
        )

    def to_policy_create(self, dataset_key: str, rule: GovernanceRuleV2) -> PolicyCreate:
        ds = rule.dataspace
        policy_id = ds.contract.access_policy_id or f"{dataset_key.replace('.', '-')}-policy"

        # Use GovernanceMapper (full ODRL v2) for the offer
        from ds.governance.mapper import GovernanceMapper
        gm = GovernanceMapper(participant_id=self.participant_id, base_url=self.base_url)
        odrl_offer = gm.to_odrl_offer(dataset_key, rule)
        odrl_set = {**odrl_offer, "@type": "odrl:Set"}

        return PolicyCreate(id=policy_id, policy=odrl_set)

    def to_contract_definition(
        self,
        dataset_key: str,
        rule: GovernanceRuleV2,
        policy_id: str,
        asset_id: str,
    ) -> ContractDefCreate:
        ds = rule.dataspace
        contract_id = ds.contract.access_policy_id or f"{dataset_key.replace('.', '-')}-contract"
        return ContractDefCreate(
            id=contract_id,
            access_policy_id=ds.contract.access_policy_id or policy_id,
            contract_policy_id=ds.contract.contract_policy_id or policy_id,
            assets_selector=[{
                "@type": "CriterionDto",
                "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                "operator": "=",
                "operandRight": asset_id,
            }],
        )

    @staticmethod
    def _infer_medallion(dataset_key: str) -> str:
        for level in ("gold", "silver", "bronze", "raw", "staging"):
            if level in dataset_key:
                return level
        return "unknown"


def load_exposed_datasets(governance_yaml_path: str) -> dict[str, GovernanceRuleV2]:
    """Load governance.yaml and return datasets where expose: true and access_level != secret."""
    path = Path(governance_yaml_path)
    resolver = GovernanceResolver.from_file(path)
    result: dict[str, GovernanceRuleV2] = {}
    for key in resolver.config.sources:
        rule = resolver.resolve(key)
        if rule.dataspace.expose and rule.access_level != "secret":
            result[key] = rule
    return result
