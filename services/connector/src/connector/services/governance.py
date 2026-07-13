"""Governance YAML → EDC payload service."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ds.governance.mapper import GovernanceMapper
from ds.governance.models import GovernanceRuleV2, OdrlProfile
from ds.governance.resolver import GovernanceResolver

from ..schemas.edc import AssetCreate, ContractDefCreate, DataAddress, PolicyCreate


class ConnectorGovernanceMapper:
    """Translates GovernanceRuleV2 into EDC Management API Pydantic objects."""

    def __init__(
        self,
        participant_id: str,
        participant_base_url: str,
        profile: OdrlProfile | None = None,
        owner_did_resolver: Callable[[str], str | None] | None = None,
    ):
        self.participant_id = participant_id
        self.base_url = participant_base_url.rstrip("/")
        self._mapper = GovernanceMapper(
            participant_id=participant_id,
            base_url=participant_base_url,
            profile=profile,
            owner_did_resolver=owner_did_resolver,
        )

    def to_asset_create(self, dataset_key: str, rule: GovernanceRuleV2) -> AssetCreate:
        ds = rule.dataspace
        asset_id = ds.asset.id or f"{self.base_url}/datasets/{dataset_key.replace('.', '/')}"
        medallion = ds.medallion or self._infer_medallion(dataset_key)
        pfx = self._mapper.profile.prefix

        extra: dict[str, str] = {}
        for k, v in ds.data_address.query_params.items():
            extra[f"queryParam:{k}"] = v

        return AssetCreate(
            id=asset_id,
            properties={
                "name": rule.title or dataset_key,
                "description": rule.description or "",
                "contenttype": ds.asset.content_type,
                f"{pfx}:medallion": medallion,
                f"{pfx}:classification": rule.classification or "",
                f"{pfx}:sourceSystem": rule.source_system or "",
                f"{pfx}:tags": ",".join(rule.tags),
                f"{pfx}:userFilterColumn": (
                    rule.row_filters[0].args.column if rule.row_filters
                    else rule.user_filter_column or ""
                ),
                f"{pfx}:rowFilters": [
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

        odrl_offer = self._mapper.to_odrl_offer(dataset_key, rule)
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
