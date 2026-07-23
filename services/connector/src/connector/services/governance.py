"""Governance YAML → EDC payload service."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ds.governance.mapper import GovernanceMapper
from ds.governance.models import GovernanceRuleV2, OdrlProfile
from ds.governance.matrix import build_policy_matrix
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

        owner_alias = rule.ownership[0].name if rule.ownership else ""
        owner_did = ""
        if owner_alias and self._mapper.owner_did_resolver:
            owner_did = self._mapper.owner_did_resolver(owner_alias) or ""

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
                f"{pfx}:owner": owner_alias,
                f"{pfx}:ownerDid": owner_did,
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
        odrl_set = self._to_edc_policy({**odrl_offer, "@type": "odrl:Set"})
        odrl_set["@id"] = policy_id
        if "odrl:assigner" not in odrl_set:
            odrl_set["odrl:assigner"] = {"@id": self.participant_id}
        odrl_set.pop("odrl:obligation", None)
        odrl_set.pop("odrl:prohibition", None)

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

    @classmethod
    def _to_edc_policy(cls, value):
        """Compact ODRL term objects where EDC's v3 policy validator expects strings."""
        if isinstance(value, list):
            return [cls._to_edc_policy(item) for item in value]
        if not isinstance(value, dict):
            return value

        result = {key: cls._to_edc_policy(item) for key, item in value.items()}
        result.pop("odrl:duty", None)
        for key in ("odrl:leftOperand",):
            nested = result.get(key)
            if isinstance(nested, dict) and "@id" in nested:
                result[key] = nested["@id"]
        constraints = result.get("odrl:constraint")
        if isinstance(constraints, list):
            result["odrl:constraint"] = [
                cls._to_edc_constraint(constraint)
                for constraint in constraints
                if not (
                    isinstance(constraint, dict)
                    and constraint.get("odrl:leftOperand") == "ds:consentStatus"
                )
            ]
        return result

    #: ``odrl:purpose`` in absolute form. The compact form must not reach EDC:
    #: it is stored verbatim as the left operand and then treated as an IRI
    #: whose scheme is ``odrl``, which JSON-LD refuses to compact
    #: (IRI_CONFUSED_WITH_PREFIX) — taking the whole DSP catalogue response down
    #: with a 500. Every other operand the mapper emits is already absolute.
    PURPOSE_OPERAND = "http://www.w3.org/ns/odrl/2/purpose"

    @classmethod
    def _to_edc_constraint(cls, constraint):
        """Make the purpose constraint safe for EDC's policy store and serialiser.

        The public ODRL offer keeps the idiomatic ``odrl:purpose`` and
        ``{"@id": <iri>}`` forms, because a purpose *is* an IRI reference and the
        offer carries an ``@context`` that defines the prefix. EDC has neither
        luxury: it stores operands as literals and re-serialises them, so the
        left operand is expanded to an absolute IRI and the right operand
        flattened to plain strings — which is also the shape
        ``ConsentStatusFunction`` reads the negotiated purposes back out of.
        """
        if not isinstance(constraint, dict):
            return constraint
        if constraint.get("odrl:leftOperand") not in ("odrl:purpose", cls.PURPOSE_OPERAND):
            return constraint

        right = constraint.get("odrl:rightOperand")
        if isinstance(right, dict) and "@id" in right:
            right = right["@id"]
        elif isinstance(right, list):
            right = [
                item["@id"] if isinstance(item, dict) and "@id" in item else item
                for item in right
            ]
        return {
            **constraint,
            "odrl:leftOperand": cls.PURPOSE_OPERAND,
            "odrl:rightOperand": right,
        }


def load_exposed_datasets(
    governance_yaml_path: str,
    overlay_name: str | None = None,
) -> dict[str, GovernanceRuleV2]:
    """Load governance.yaml (with optional overlay) and return datasets where expose: true and access_level != secret."""
    path = Path(governance_yaml_path)
    resolver = GovernanceResolver.from_file_with_override(path, overlay_name=overlay_name)
    result: dict[str, GovernanceRuleV2] = {}
    for key in resolver.config.sources:
        rule = resolver.resolve(key)
        if rule.dataspace.expose and rule.access_level != "secret":
            result[key] = rule
    return result


def load_governance_policy_matrix(
    governance_yaml_path: str,
    participant_id: str,
    participant_base_url: str,
    profile: OdrlProfile | None = None,
    overlay_name: str | None = None,
) -> list[dict[str, Any]]:
    """Load exposed datasets and return the explainable governance matrix."""
    datasets = load_exposed_datasets(governance_yaml_path, overlay_name=overlay_name)
    mapper = GovernanceMapper(participant_id=participant_id, base_url=participant_base_url, profile=profile)
    return build_policy_matrix(datasets, mapper)
