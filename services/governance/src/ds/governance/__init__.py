"""Governance v2 — ODRL-aware policy model for the dataspaces platform."""

from .models import (
    GovernanceOwner,
    GovernanceRule,
    GovernanceRuleV2,
    DataspacePolicy,
    DataspaceSpec,
    PolicyObligations,
    PolicyAudience,
    PolicyConsent,
    DataspaceAsset,
    DataspaceDataAddress,
    DataspaceContract,
)
from .resolver import GovernanceConfig, GovernanceResolver
from .mapper import GovernanceMapper
from .matrix import build_policy_matrix, build_policy_matrix_entry

__all__ = [
    "GovernanceOwner",
    "GovernanceRule",
    "GovernanceRuleV2",
    "DataspacePolicy",
    "DataspaceSpec",
    "PolicyObligations",
    "PolicyAudience",
    "PolicyConsent",
    "DataspaceAsset",
    "DataspaceDataAddress",
    "DataspaceContract",
    "GovernanceConfig",
    "GovernanceResolver",
    "GovernanceMapper",
    "build_policy_matrix",
    "build_policy_matrix_entry",
]
