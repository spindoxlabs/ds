"""Map DCAT-AP datasets to EDC Management API payloads.

Two paths:
1. ODRL pass-through — the DCAT source already includes an ODRL offer
   in dcat:distribution → odrl:hasPolicy.  Extract it, convert Offer → Set.
2. Governance overrides — catalogues.yaml `defaults` provide governance-like
   fields.  Build a minimal ODRL Set from those fields.
"""
from __future__ import annotations

from typing import Any


def dcat_to_edc_payloads(
    dataset: dict[str, Any],
    source_defaults: dict[str, Any],
) -> dict[str, Any] | None:
    """Convert a DCAT-AP dataset dict to EDC asset + policy + contract payloads.

    Returns a dict with keys "asset", "policy", "contract_definition",
    or None if the dataset should be skipped (e.g. access_level=secret).
    """
    dataset_id = dataset.get("@id") or dataset.get("id") or ""
    if not dataset_id:
        return None

    title = dataset.get("dct:title") or dataset.get("title") or dataset_id
    description = dataset.get("dct:description") or dataset.get("description") or ""
    keywords = dataset.get("dcat:keyword") or dataset.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]

    access_level = (
        dataset.get("ds:accessLevel")
        or dataset.get("accessLevel")
        or source_defaults.get("access_level", "internal")
    )
    if access_level == "secret":
        return None

    odrl_offer = _extract_odrl_offer(dataset)

    if odrl_offer:
        policy_body = _offer_to_set(odrl_offer, dataset_id)
    else:
        policy_body = _build_policy_from_defaults(dataset_id, source_defaults)

    asset_id = dataset_id
    policy_id = f"{dataset_id}:policy"
    contract_id = f"{dataset_id}:contract"

    data_address = _build_data_address(dataset, source_defaults)

    asset = {
        "@id": asset_id,
        "properties": {
            "name": title,
            "description": description,
            "contenttype": "application/json",
            "dct:keyword": keywords,
        },
        "dataAddress": data_address,
    }

    policy = {
        "@id": policy_id,
        "policy": policy_body,
    }

    contract_definition = {
        "@id": contract_id,
        "accessPolicyId": policy_id,
        "contractPolicyId": policy_id,
        "assetsSelector": {
            "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
            "operator": "=",
            "operandRight": asset_id,
        },
    }

    return {
        "asset": asset,
        "policy": policy,
        "contract_definition": contract_definition,
    }


def _extract_odrl_offer(dataset: dict) -> dict | None:
    """Extract ODRL offer from DCAT distribution, if present."""
    distributions = dataset.get("dcat:distribution") or dataset.get("distribution") or []
    if isinstance(distributions, dict):
        distributions = [distributions]

    for dist in distributions:
        policy = dist.get("odrl:hasPolicy") or dist.get("hasPolicy")
        if policy:
            if isinstance(policy, list):
                policy = policy[0]
            return policy
    return None


def _offer_to_set(offer: dict, target: str) -> dict:
    """Convert an ODRL Offer to an ODRL Set (EDC requires Set for PolicyDefinition)."""
    policy = dict(offer)
    policy["@type"] = "odrl:Set"
    policy.pop("@id", None)
    if "odrl:target" not in policy and "target" not in policy:
        policy["odrl:target"] = {"@id": target}
    return policy


def _build_policy_from_defaults(
    target: str,
    defaults: dict[str, Any],
) -> dict:
    """Build a minimal ODRL Set from governance-like defaults."""
    permissions: list[dict] = []

    permission: dict[str, Any] = {
        "odrl:action": {"@id": "odrl:use"},
        "odrl:target": {"@id": target},
    }

    constraints: list[dict] = []

    access_requirements = defaults.get("access_requirements", "")
    if access_requirements in ("partner", "contract"):
        constraints.append({
            "odrl:leftOperand": {"@id": "https://w3id.org/dsp/policy/Membership"},
            "odrl:operator": {"@id": "odrl:eq"},
            "odrl:rightOperand": {"@value": "active", "@type": "xsd:string"},
        })

    consent_required = defaults.get("consent_required", False)
    if consent_required:
        constraints.append({
            "odrl:leftOperand": {"@id": "https://w3id.org/dsp/policy/ConsentStatus"},
            "odrl:operator": {"@id": "odrl:eq"},
            "odrl:rightOperand": {"@value": "active", "@type": "xsd:string"},
        })

    if constraints:
        permission["odrl:constraint"] = constraints

    permissions.append(permission)

    obligations: list[dict] = []
    retention_days = defaults.get("retention_days")
    if retention_days:
        obligations.append({
            "odrl:action": [{
                "rdf:value": {"@id": "odrl:delete"},
                "odrl:refinement": [{
                    "odrl:leftOperand": {"@id": "odrl:delayPeriod"},
                    "odrl:operator": {"@id": "odrl:lteq"},
                    "odrl:rightOperand": {
                        "@value": f"P{retention_days}D",
                        "@type": "xsd:duration",
                    },
                }],
            }],
        })

    policy: dict[str, Any] = {
        "@type": "odrl:Set",
        "odrl:permission": permissions,
    }
    if obligations:
        policy["odrl:obligation"] = obligations

    return policy


def _build_data_address(dataset: dict, defaults: dict[str, Any]) -> dict:
    """Build EDC dataAddress from DCAT distribution or source defaults."""
    da_defaults = defaults.get("data_address") or {}

    distributions = dataset.get("dcat:distribution") or dataset.get("distribution") or []
    if isinstance(distributions, dict):
        distributions = [distributions]

    base_url = da_defaults.get("base_url", "")
    for dist in distributions:
        access_url = dist.get("dcat:accessURL") or dist.get("accessURL")
        if access_url:
            if isinstance(access_url, dict):
                access_url = access_url.get("@id", "")
            base_url = base_url or access_url
            break

    return {
        "type": da_defaults.get("type", "HttpData"),
        "baseUrl": base_url,
        "proxyPath": str(da_defaults.get("proxy_path", False)).lower(),
        "proxyQueryParams": str(da_defaults.get("proxy_query_params", True)).lower(),
    }
