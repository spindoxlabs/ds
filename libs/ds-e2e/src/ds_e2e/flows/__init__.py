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
from ds_e2e.flows.fail_closed import FailClosedFlow
from ds_e2e.flows.lineage import LineageFlow
from ds_e2e.flows.org_onboarding import OrgOnboardingFlow
from ds_e2e.flows.smoke import SmokeFlow
from ds_e2e.flows.two_providers import TwoProvidersFlow
from ds_e2e.flows.uc1 import UC1Flow
from ds_e2e.flows.uc2 import UC2Flow
from ds_e2e.flows.uc3 import UC3Flow
from ds_e2e.flows.user_authority import UserAuthorityFlow

# Ordered cheapest-and-most-fundamental first: a failing contract or trust-chain
# assertion explains most downstream failures, so `--flow all` surfaces it before
# spending minutes on DSP round trips.
FLOW_REGISTRY: dict[str, type[BaseFlow]] = {
    "api-contract": ApiContractFlow,
    "authz-perimeter": AuthzPerimeterFlow,
    "user-authority": UserAuthorityFlow,
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
    "two-providers": TwoProvidersFlow,
    "smoke": SmokeFlow,
    # **Last, and deliberately.** It stops a container and restarts it, so it is
    # the one flow whose failure mode is *the next flow fails for reasons of its
    # own*. Running it last bounds that to zero, and `runner.run_flow` calls
    # `cleanup()` in a `finally` so an exception mid-outage still restores the
    # PDP. It also has to run after `two-providers`: both negotiate the same
    # consumer/asset pair, and this one revokes the request the other leaves
    # behind (`REV-03`).
    "fail-closed": FailClosedFlow,
}

# The delegation chains. They assert against `ds-e2e scenario apply` fixtures
# and clean up their own consent rows, so the set is re-runnable in place.
CHAIN_FLOWS: tuple[str, ...] = (
    "chain-community",
    "chain-partner",
    "chain-unbundling",
)

# Flows that need no **EDC** and no completed data exchange — the set worth
# running on every change.
#
# Not "runs on a partial stack" (`E2E-09`): the comment said that before
# `CHAIN_FLOWS` was folded in, and the three chain flows need the delegation
# scenario applied (`task e2e:scenario:apply`, which `e2e:fast` now declares as
# a dep). They still need no EDC, so the *stated* property held while the
# implied one — "nothing to set up first" — quietly stopped being true, and the
# chains failed on missing fixtures for whoever ran `e2e:fast` first on a fresh
# stack.
FAST_FLOWS: tuple[str, ...] = (
    "api-contract",
    "authz-perimeter",
    "user-authority",
    "dcp-trust",
    "consent-purpose",
    "consent-request",
    "org-onboarding",
    *CHAIN_FLOWS,
)

# The security subset: what the API refuses, rather than what it does.
SECURITY_FLOWS: tuple[str, ...] = (
    "api-contract",
    "authz-perimeter",
    "user-authority",
    "dcp-trust",
)

__all__ = [
    "FLOW_REGISTRY",
    "FAST_FLOWS",
    "SECURITY_FLOWS",
    "CHAIN_FLOWS",
    "BaseFlow",
]
