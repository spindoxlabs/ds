from __future__ import annotations

from ds_e2e.flows.api_contract import ApiContractFlow
from ds_e2e.flows.authz_perimeter import AuthzPerimeterFlow
from ds_e2e.flows.base import BaseFlow
from ds_e2e.flows.catalog_discovery import CatalogDiscoveryFlow
from ds_e2e.flows.chains import (
    ChainCommunityFlow,
    ChainPartnerFlow,
    ChainUnbundlingFlow,
)
from ds_e2e.flows.consent_purpose import ConsentPurposeFlow
from ds_e2e.flows.consent_request import ConsentRequestFlow
from ds_e2e.flows.dcp_trust import DcpTrustFlow
from ds_e2e.flows.lineage import LineageFlow
from ds_e2e.flows.org_onboarding import OrgOnboardingFlow
from ds_e2e.flows.smoke import SmokeFlow
from ds_e2e.flows.uc1 import UC1Flow
from ds_e2e.flows.uc2 import UC2Flow
from ds_e2e.flows.uc3 import UC3Flow

# Ordered cheapest-and-most-fundamental first: a failing contract or trust-chain
# assertion explains most downstream failures, so `--flow all` surfaces it before
# spending minutes on DSP round trips.
FLOW_REGISTRY: dict[str, type[BaseFlow]] = {
    "api-contract": ApiContractFlow,
    "authz-perimeter": AuthzPerimeterFlow,
    "dcp-trust": DcpTrustFlow,
    "consent-purpose": ConsentPurposeFlow,
    "consent-request": ConsentRequestFlow,
    "org-onboarding": OrgOnboardingFlow,
    "uc1": UC1Flow,
    "uc2": UC2Flow,
    "uc3": UC3Flow,
    "chain-community": ChainCommunityFlow,
    "chain-partner": ChainPartnerFlow,
    "chain-unbundling": ChainUnbundlingFlow,
    "catalog-discovery": CatalogDiscoveryFlow,
    "lineage": LineageFlow,
    "smoke": SmokeFlow,
}

# The delegation chains. They assert against `ds-e2e scenario apply` fixtures
# and clean up their own consent rows, so the set is re-runnable in place.
CHAIN_FLOWS: tuple[str, ...] = (
    "chain-community",
    "chain-partner",
    "chain-unbundling",
)

# Flows that need neither the EDC nor a completed data exchange — the set that
# runs on a partial stack, and the set worth running on every change.
FAST_FLOWS: tuple[str, ...] = (
    "api-contract",
    "authz-perimeter",
    "dcp-trust",
    "consent-purpose",
    "consent-request",
    "org-onboarding",
    *CHAIN_FLOWS,
)

# The security subset: what the API refuses, rather than what it does.
SECURITY_FLOWS: tuple[str, ...] = ("api-contract", "authz-perimeter", "dcp-trust")

__all__ = [
    "FLOW_REGISTRY",
    "FAST_FLOWS",
    "SECURITY_FLOWS",
    "CHAIN_FLOWS",
    "BaseFlow",
]
