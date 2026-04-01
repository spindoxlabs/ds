"""Tests for GovernanceMapper — ODRL offer and EDC payload generation."""
import pytest

from ds.governance.mapper import GovernanceMapper
from ds.governance.models import (
    DataspaceAsset,
    DataspacePolicy,
    DataspaceSpec,
    GovernanceRuleV2,
    PolicyConsent,
    PolicyObligations,
)

PARTICIPANT = "provider"
BASE_URL = "https://provider.dataspaces.localhost"


def _mapper() -> GovernanceMapper:
    return GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL)


def _rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


# ── ODRL Offer ────────────────────────────────────────────────────────────────

def test_odrl_offer_basic_structure():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    offer = mapper.to_odrl_offer("datasets.gold.meters", rule)

    assert offer["@type"] == "odrl:Offer"
    assert "provider" in offer["@id"]
    assert "odrl:permission" in offer
    assert "odrl:prohibition" in offer
    assert "odrl:obligation" in offer


def test_open_level_permits_transfer():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    actions = [p["odrl:action"]["@id"] for p in offer["odrl:permission"]]
    assert "odrl:transfer" in actions
    assert "ds:query" in actions


def test_restricted_level_only_query():
    mapper = _mapper()
    rule = _rule(access_level="restricted", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    actions = [p["odrl:action"]["@id"] for p in offer["odrl:permission"]]
    assert actions == ["ds:query"]


def test_secret_level_no_permissions():
    mapper = _mapper()
    rule = _rule(access_level="secret", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:permission"] == []


def test_pii_prohibits_transfer_and_sublicense():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="pii")
    offer = mapper.to_odrl_offer("ds", rule)

    prohibited_actions = [p["odrl:action"]["@id"] for p in offer["odrl:prohibition"]]
    assert "odrl:transfer" in prohibited_actions
    assert "odrl:sublicense" in prohibited_actions


def test_purpose_derived_from_tags():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", tags=["grid"])
    offer = mapper.to_odrl_offer("ds", rule)

    constraints = [
        c for p in offer["odrl:permission"]
        for c in p.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
    ]
    assert any("GridMonitoring" in c["odrl:rightOperand"]["@id"] for c in constraints)


def test_consent_duty_added_when_user_filter_column_set():
    mapper = _mapper()
    rule = _rule(
        access_level="restricted",
        classification="pii",
        user_filter_column="sub",
    )
    offer = mapper.to_odrl_offer("ds", rule)

    for perm in offer["odrl:permission"]:
        duties = perm.get("odrl:duty", [])
        assert any(d["odrl:action"]["@id"] == "odrl:obtainConsent" for d in duties)


def test_consent_constraint_added_when_user_filter_column_set():
    mapper = _mapper()
    rule = _rule(access_level="restricted", classification="pii", user_filter_column="sub")
    offer = mapper.to_odrl_offer("ds", rule)

    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        consent_constraints = [
            c for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == "ds:consentStatus"
        ]
        assert len(consent_constraints) == 1
        assert consent_constraints[0]["odrl:rightOperand"] == "active"


def test_retention_days_adds_delete_obligation():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", retention_days=30)
    offer = mapper.to_odrl_offer("ds", rule)

    obligations = offer["odrl:obligation"]
    delete_obs = [o for o in obligations if o["odrl:action"]["@id"] == "odrl:delete"]
    assert len(delete_obs) == 1
    assert "P30D" in delete_obs[0]["odrl:constraint"][0]["odrl:rightOperand"]["@value"]


def test_attribution_obligation_added():
    mapper = _mapper()
    rule = _rule(
        access_level="open",
        classification="green",
        attribution="https://provider.example/credit",
        policy=DataspacePolicy(
            obligations=PolicyObligations(attribution=True)
        ),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    obligations = offer["odrl:obligation"]
    attr_obs = [o for o in obligations if o["odrl:action"]["@id"] == "odrl:attribute"]
    assert len(attr_obs) == 1


# ── EDC Asset ─────────────────────────────────────────────────────────────────

def test_asset_create_basic():
    mapper = _mapper()
    rule = _rule(
        title="Meter Readings",
        access_level="internal",
        classification="green",
        tags=["meters"],
    )
    asset = mapper.to_asset_create("datasets.gold.meters", rule)

    assert asset["@type"] == "Asset"
    assert asset["properties"]["name"] == "Meter Readings"
    assert asset["properties"]["ds:classification"] == "green"
    assert asset["properties"]["ds:medallion"] == "gold"
    assert "meters" in asset["properties"]["ds:tags"]


def test_asset_id_inferred_from_base_url():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    asset = mapper.to_asset_create("datasets.gold.meters", rule)
    assert asset["@id"].startswith(BASE_URL)


def test_asset_id_overridden_by_spec():
    mapper = _mapper()
    rule = _rule(
        access_level="internal",
        classification="green",
        dataspace=DataspaceSpec(asset=DataspaceAsset(id="custom-asset-id")),
    )
    asset = mapper.to_asset_create("datasets.gold.meters", rule)
    assert asset["@id"] == "custom-asset-id"


# ── EDC Policy Definition ─────────────────────────────────────────────────────

def test_policy_create_type():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    policy_def = mapper.to_policy_create("datasets.gold.meters", rule)
    assert policy_def["@type"] == "PolicyDefinition"
    assert policy_def["policy"]["@type"] == "odrl:Set"


# ── EDC Contract Definition ───────────────────────────────────────────────────

def test_contract_definition_structure():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    contract = mapper.to_contract_definition(
        "datasets.gold.meters", rule,
        policy_id="meters-policy",
        asset_id="https://provider.example/datasets/meters",
    )
    assert contract["@type"] == "ContractDefinition"
    assert len(contract["assetsSelector"]) == 1
    assert contract["assetsSelector"][0]["operandRight"] == "https://provider.example/datasets/meters"


# ── Purpose derivation ────────────────────────────────────────────────────────

def test_derive_purposes_from_multiple_tags():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", tags=["rec", "grid", "meters"])
    offer = mapper.to_odrl_offer("ds", rule)

    purpose_values = [
        c["odrl:rightOperand"]["@id"]
        for p in offer["odrl:permission"]
        for c in p.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
    ]
    assert "ds:purpose:EnergyBalancing" in purpose_values
    assert "ds:purpose:GridMonitoring" in purpose_values
    # deduplication: rec and meters both map to EnergyBalancing
    assert purpose_values.count("ds:purpose:EnergyBalancing") == len(offer["odrl:permission"])


def test_medallion_inference():
    mapper = _mapper()
    for key, expected in [
        ("datasets.gold.x", "gold"),
        ("datasets.silver.y", "silver"),
        ("raw.data", "raw"),
        ("mystery", "unknown"),
    ]:
        rule = _rule(access_level="open", classification="green")
        asset = mapper.to_asset_create(key, rule)
        assert asset["properties"]["ds:medallion"] == expected, f"failed for {key}"
