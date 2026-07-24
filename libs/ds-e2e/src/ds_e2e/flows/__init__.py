from __future__ import annotations

from ds_e2e.flows.base import BaseFlow
from ds_e2e.flows.consent_purpose import ConsentPurposeFlow
from ds_e2e.flows.org_onboarding import OrgOnboardingFlow
from ds_e2e.flows.smoke import SmokeFlow
from ds_e2e.flows.uc1 import UC1Flow
from ds_e2e.flows.uc2 import UC2Flow
from ds_e2e.flows.uc3 import UC3Flow

FLOW_REGISTRY: dict[str, type[BaseFlow]] = {
    "smoke": SmokeFlow,
    "consent-purpose": ConsentPurposeFlow,
    "org-onboarding": OrgOnboardingFlow,
    "uc1": UC1Flow,
    "uc2": UC2Flow,
    "uc3": UC3Flow,
}

__all__ = ["FLOW_REGISTRY", "BaseFlow"]
