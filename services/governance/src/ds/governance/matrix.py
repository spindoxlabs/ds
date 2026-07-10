"""Governance policy matrix generation.

The matrix is the explainable bridge between a governance rule and the runtime
enforcement surfaces used by this dataspace implementation.
"""
from __future__ import annotations

from typing import Any

from .mapper import GovernanceMapper
from .models import GovernanceRuleV2


def _id_of(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("@id") or value.get("id") or value)
    return str(value)


def _permission_constraints(policy: dict[str, Any]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for permission in policy.get("odrl:permission") or []:
        for constraint in permission.get("odrl:constraint") or []:
            constraints.append(constraint)
    return constraints


def _constraint_summary(constraint: dict[str, Any]) -> dict[str, str]:
    return {
        "left_operand": _id_of(constraint.get("odrl:leftOperand", "")),
        "operator": _id_of(constraint.get("odrl:operator", "")),
        "right_operand": _id_of(constraint.get("odrl:rightOperand", "")),
    }


def _row_filter_columns(rule: GovernanceRuleV2) -> list[str]:
    columns = [row_filter.args.column for row_filter in rule.row_filters]
    if rule.user_filter_column and rule.user_filter_column not in columns:
        columns.append(rule.user_filter_column)
    return columns


def build_policy_matrix_entry(
    dataset_key: str,
    rule: GovernanceRuleV2,
    mapper: GovernanceMapper,
) -> dict[str, Any]:
    """Return an explainable matrix entry for one dataset rule."""
    odrl_offer = mapper.to_odrl_offer(dataset_key, rule)
    asset = mapper.to_asset_create(dataset_key, rule)
    policy = mapper.to_policy_create(dataset_key, rule)
    contract = mapper.to_contract_definition(
        dataset_key,
        rule,
        policy_id=str(policy.get("@id")),
        asset_id=str(asset.get("@id")),
    )

    constraints = [_constraint_summary(c) for c in _permission_constraints(odrl_offer)]
    purpose = sorted({
        c["right_operand"]
        for c in constraints
        if c["left_operand"] == "odrl:purpose"
    })
    edc_constraints = [
        c for c in constraints
        if c["left_operand"] in {"ds:accessScope", "ds:contractRequired"}
    ]
    app_constraints = [
        c for c in constraints
        if c["left_operand"] in {"odrl:purpose", "ds:consentStatus"}
    ]

    access_level = rule.access_level or "internal"
    row_filter_columns = _row_filter_columns(rule)
    requires_consent = (
        rule.policy.consent.required
        or bool(rule.row_filters)
        or bool(rule.user_filter_column)
        or (rule.classification == "pii")
    )

    return {
        "dataset_key": dataset_key,
        "title": rule.title or dataset_key,
        "asset_id": asset.get("@id"),
        "exposed": bool(rule.dataspace.expose and access_level != "secret"),
        "access_level": access_level,
        "classification": rule.classification or "green",
        "purpose": purpose,
        "permitted_actions": [
            _id_of(permission.get("odrl:action", ""))
            for permission in odrl_offer.get("odrl:permission") or []
        ],
        "prohibited_actions": [
            _id_of(prohibition.get("odrl:action", ""))
            for prohibition in odrl_offer.get("odrl:prohibition") or []
        ],
        "obligations": [
            _id_of(obligation.get("odrl:action", ""))
            for obligation in odrl_offer.get("odrl:obligation") or []
        ],
        "required_scope": rule.policy.audience.required_scope
        if access_level in {"internal", "restricted"} else None,
        "contract_required": access_level == "restricted"
        or rule.policy.obligations.contract_required,
        "consent": {
            "required": requires_consent,
            "scope": rule.policy.consent.scope,
            "on_revocation": rule.policy.consent.on_revocation,
            "row_filter_columns": row_filter_columns,
        },
        "odrl_constraints": constraints,
        "edc_policy": {
            "policy_id": policy.get("@id"),
            "contract_definition_id": contract.get("@id"),
            "enforced_constraints": edc_constraints,
            "enforced_by": "EDC policy engine via edc-extensions",
        },
        "connector_enforcement": {
            "constraints": app_constraints,
            "checks": [
                "user VC verification on consumer and consent endpoints",
                "duplicate active request/transfer prevention",
                "agreement and transfer revocation state",
            ],
        },
        "dataset_api_enforcement": {
            "checks": [
                "EDR JWT validation",
                "transfer/agreement active status check",
                "row-level consent filter",
            ] if requires_consent else [
                "EDR JWT validation",
                "transfer/agreement active status check",
            ],
        },
    }


def build_policy_matrix(
    rules: dict[str, GovernanceRuleV2],
    mapper: GovernanceMapper,
) -> list[dict[str, Any]]:
    """Return matrix entries sorted by dataset key."""
    return [
        build_policy_matrix_entry(dataset_key, rules[dataset_key], mapper)
        for dataset_key in sorted(rules)
    ]
