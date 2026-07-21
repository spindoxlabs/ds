"""Tests for GovernanceMapper — ODRL offer and EDC payload generation."""
import pytest

from ds.governance.mapper import GovernanceMapper
from ds.governance.models import (
    DataspaceAsset,
    DataspacePolicy,
    DataspaceSpec,
    GovernanceOwner,
    GovernanceRuleV2,
    OdrlProfile,
    PolicyAudience,
    PolicyConsent,
    PolicyObligations,
    PurposeConcept,
)

PARTICIPANT = "provider"
BASE_URL = "https://provider.dataspaces.localhost"

# Default profile for assertions
_P = OdrlProfile()

# Energy-domain profile used by tests that exercise tag→purpose derivation
_ENERGY_PROFILE = OdrlProfile(
    tag_to_purpose={
        "rec": "EnergyBalancing",
        "meters": "EnergyBalancing",
        "grid": "GridMonitoring",
        "tourism": "UrbanPlanning",
        "mobility": "UrbanPlanning",
    },
    purposes=[
        PurposeConcept(slug="EnergyBalancing", label="Energy Community Balancing"),
        PurposeConcept(slug="GridMonitoring", label="Grid Monitoring"),
        PurposeConcept(slug="UrbanPlanning", label="Urban Planning"),
    ],
)


def _mapper(**kwargs) -> GovernanceMapper:
    return GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL, **kwargs)


def _rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


def _constraints(offer: dict) -> list[dict]:
    return [
        c
        for perm in offer.get("odrl:permission", [])
        for c in perm.get("odrl:constraint", [])
    ]


def _left_op(constraint: dict) -> str:
    lo = constraint.get("odrl:leftOperand")
    if isinstance(lo, dict):
        return lo.get("@id", "")
    return lo or ""


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


def test_odrl_context_uses_profile_prefix():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    ctx = offer["@context"]
    assert ctx[_P.prefix] == _P.namespace
    assert "odrl" in ctx


def test_open_level_permits_transfer():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    actions = [p["odrl:action"]["@id"] for p in offer["odrl:permission"]]
    assert "odrl:transfer" in actions
    assert _P.term(_P.query_action) in actions


def test_restricted_level_only_query():
    mapper = _mapper()
    rule = _rule(access_level="restricted", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    actions = [p["odrl:action"]["@id"] for p in offer["odrl:permission"]]
    assert actions == [_P.term(_P.query_action)]


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
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(access_level="open", classification="green", tags=["grid"])
    offer = mapper.to_odrl_offer("ds", rule)

    constraints = [
        c for p in offer["odrl:permission"]
        for c in p.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
    ]
    assert any("GridMonitoring" in c["odrl:rightOperand"]["@id"] for c in constraints)


def test_purpose_uses_profile_namespace():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(access_level="open", classification="green", tags=["grid"])
    offer = mapper.to_odrl_offer("ds", rule)

    constraints = [
        c for p in offer["odrl:permission"]
        for c in p.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
    ]
    assert all(c["odrl:rightOperand"]["@id"].startswith(_P.namespace) for c in constraints)


def test_no_purpose_constraints_without_tag_mapping():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", tags=["grid"])
    offer = mapper.to_odrl_offer("ds", rule)

    for perm in offer["odrl:permission"]:
        purpose_constraints = [
            c for c in perm.get("odrl:constraint", [])
            if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
        ]
        assert len(purpose_constraints) == 0


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

    consent_operand = _P.term(_P.consent_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        consent_constraints = [
            c for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == consent_operand
        ]
        assert len(consent_constraints) == 1
        assert consent_constraints[0]["odrl:rightOperand"]["@value"] == "active"


def test_retention_days_adds_delete_obligation_with_delay_period():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", retention_days=30)
    offer = mapper.to_odrl_offer("ds", rule)

    obligations = offer["odrl:obligation"]
    assert len(obligations) == 1
    action_block = obligations[0]["odrl:action"]
    assert isinstance(action_block, list)
    refinement = action_block[0]["odrl:refinement"][0]
    assert refinement["odrl:leftOperand"]["@id"] == "odrl:delayPeriod"
    assert refinement["odrl:operator"]["@id"] == "odrl:lteq"
    assert refinement["odrl:rightOperand"]["@value"] == "P30D"
    assert refinement["odrl:rightOperand"]["@type"] == "xsd:duration"


def test_attribution_obligation_uses_attribute_to():
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
    attr_obs = [o for o in obligations if o["odrl:action"]["@id"] == "odrl:attributeTo"]
    assert len(attr_obs) == 1
    assert "odrl:attributeTo" in attr_obs[0]


# ── access_requirements → constraints ────────────────────────────────────────

def test_access_requirements_all_no_membership_constraint():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", access_requirements="all")
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [c for c in constraints if c.get("odrl:leftOperand", {}).get("@id") == membership_operand]
        assert len(membership) == 0


def test_access_requirements_partner_adds_membership_constraint():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", access_requirements="partner")
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [c for c in constraints if c.get("odrl:leftOperand", {}).get("@id") == membership_operand]
        assert len(membership) == 1


def test_access_requirements_contract_adds_membership_and_contract():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", access_requirements="contract")
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [c for c in constraints if c.get("odrl:leftOperand", {}).get("@id") == membership_operand]
        contract = [c for c in constraints if c.get("odrl:leftOperand", {}).get("@id") == "odrl:industry"]
        assert len(membership) == 1
        assert len(contract) == 1
        assert contract[0]["odrl:rightOperand"]["@value"] == "contract-agreed"


def test_internal_access_level_adds_membership_even_without_access_requirements():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [c for c in constraints if c.get("odrl:leftOperand", {}).get("@id") == membership_operand]
        assert len(membership) == 1


# ── Owner DID resolution ─────────────────────────────────────────────────────

def test_assigner_uses_owner_did_when_resolver_provided():
    did = "did:web:greenland.dataspaces.localhost"
    mapper = _mapper(owner_did_resolver=lambda name: did if name == "Greenland" else None)
    rule = _rule(
        access_level="open",
        classification="green",
        ownership=[GovernanceOwner(name="Greenland")],
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:assigner"]["@id"] == did


def test_assigner_falls_back_to_participant_did():
    mapper = _mapper(owner_did_resolver=lambda name: None)
    rule = _rule(
        access_level="open",
        classification="green",
        ownership=[GovernanceOwner(name="Unknown")],
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:assigner"]["@id"] == f"did:web:{PARTICIPANT}.dataspaces.localhost"


def test_assigner_default_without_resolver():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:assigner"]["@id"] == f"did:web:{PARTICIPANT}.dataspaces.localhost"


# ── Owner-relative scope generation ─────────────────────────────────────────

def _membership_scope_values(offer: dict) -> list[str]:
    """Extract all membership right-operand values across permissions."""
    values = []
    for perm in offer.get("odrl:permission", []):
        for c in perm.get("odrl:constraint", []):
            if _left_op(c) == _P.term(_P.membership_operand):
                values.append(c["odrl:rightOperand"]["@value"])
    return values


def test_owner_scope_member_when_internal():
    mapper = _mapper()
    rule = _rule(
        access_level="internal",
        classification="green",
        ownership=[GovernanceOwner(name="example-org")],
    )
    offer = mapper.to_odrl_offer("ds", rule)
    values = _membership_scope_values(offer)
    assert len(values) >= 1
    assert all(v == "owner:example-org:member" for v in values)


def test_owner_scope_partner_when_partner_requirements():
    mapper = _mapper()
    rule = _rule(
        access_level="internal",
        access_requirements="partner",
        classification="green",
        ownership=[GovernanceOwner(name="example-org")],
    )
    offer = mapper.to_odrl_offer("ds", rule)
    values = _membership_scope_values(offer)
    assert len(values) >= 1
    assert all(v == "owner:example-org:partner" for v in values)


def test_no_ownership_uses_required_scope():
    mapper = _mapper()
    rule = _rule(
        access_level="internal",
        classification="green",
    )
    offer = mapper.to_odrl_offer("ds", rule)
    values = _membership_scope_values(offer)
    assert len(values) >= 1
    assert all(v == "dataspaces.query" for v in values)


# ── @id wrapping consistency ─────────────────────────────────────────────────

def test_id_wrapping_consistent_across_constraints():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="restricted",
        classification="green",
        tags=["grid"],
        user_filter_column="sub",
    )
    offer = mapper.to_odrl_offer("ds", rule)

    for perm in offer["odrl:permission"]:
        for c in perm.get("odrl:constraint", []):
            assert isinstance(c["odrl:leftOperand"], dict), f"leftOperand not wrapped: {c}"
            assert "@id" in c["odrl:leftOperand"], f"leftOperand missing @id: {c}"


# ── Custom profile ───────────────────────────────────────────────────────────

def test_custom_profile_namespace_in_odrl():
    profile = OdrlProfile(
        namespace="https://w3id.org/catenax/policy/",
        prefix="cx-policy",
        tag_to_purpose={"grid": "GridMonitoring"},
    )
    mapper = _mapper(profile=profile)
    rule = _rule(access_level="internal", classification="green", tags=["grid"])
    offer = mapper.to_odrl_offer("ds", rule)

    ctx = offer["@context"]
    assert ctx["cx-policy"] == "https://w3id.org/catenax/policy/"

    # Membership constraint uses custom namespace
    for perm in offer["odrl:permission"]:
        for c in perm.get("odrl:constraint", []):
            lo = c["odrl:leftOperand"]["@id"]
            if "Membership" in lo:
                assert lo.startswith("https://w3id.org/catenax/policy/")


def test_profile_iri_included_in_context():
    profile = OdrlProfile(profile_iri="dsp-policy:profile2025")
    mapper = _mapper(profile=profile)
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    assert offer["@context"]["odrl:profile"] == "dsp-policy:profile2025"


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
    assert asset["properties"][f"{_P.prefix}:classification"] == "green"
    assert asset["properties"][f"{_P.prefix}:medallion"] == "gold"
    assert "meters" in asset["properties"][f"{_P.prefix}:tags"]


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
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(access_level="open", classification="green", tags=["rec", "grid", "meters"])
    offer = mapper.to_odrl_offer("ds", rule)

    purpose_values = [
        c["odrl:rightOperand"]["@id"]
        for p in offer["odrl:permission"]
        for c in p.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
    ]
    assert _P.purpose_iri("EnergyBalancing") in purpose_values
    assert _P.purpose_iri("GridMonitoring") in purpose_values
    # deduplication: rec and meters both map to EnergyBalancing
    assert purpose_values.count(_P.purpose_iri("EnergyBalancing")) == len(offer["odrl:permission"])


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
        assert asset["properties"][f"{_P.prefix}:medallion"] == expected, f"failed for {key}"


# ── OdrlProfile model ────────────────────────────────────────────────────────

def test_profile_defaults_produce_valid_iris():
    p = OdrlProfile()
    assert p.term("Membership") == "https://w3id.org/dsp/policy/Membership"
    assert p.purpose_iri("EnergyBalancing") == "https://w3id.org/dsp/policy/purpose:EnergyBalancing"


def test_profile_custom_namespace():
    p = OdrlProfile(namespace="https://example.org/policy/", prefix="ex")
    assert p.term("Membership") == "https://example.org/policy/Membership"
    assert p.purpose_iri("Test") == "https://example.org/policy/purpose:Test"


# ── Domain-neutral: manufacturing profile ─────────────────────────────────────

def test_manufacturing_profile_produces_correct_purposes():
    mfg_profile = OdrlProfile(
        namespace="https://example.org/manufacturing/policy/",
        prefix="mfg-policy",
        tag_to_purpose={
            "quality": "QualityAssurance",
            "logistics": "SupplyChain",
            "maintenance": "PredictiveMaintenance",
        },
    )
    mapper = _mapper(profile=mfg_profile)
    rule = _rule(access_level="internal", classification="green", tags=["quality", "logistics"])
    offer = mapper.to_odrl_offer("ds", rule)

    ctx = offer["@context"]
    assert ctx["mfg-policy"] == "https://example.org/manufacturing/policy/"

    purpose_iris = [
        c["odrl:rightOperand"]["@id"]
        for p in offer["odrl:permission"]
        for c in p.get("odrl:constraint", [])
        if c.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose"
    ]
    assert "https://example.org/manufacturing/policy/purpose:QualityAssurance" in purpose_iris
    assert "https://example.org/manufacturing/policy/purpose:SupplyChain" in purpose_iris


# ── Participant DID override (deployments outside the dev domain) ────────────

def test_participant_did_override_used_as_assigner():
    mapper = GovernanceMapper(
        participant_id="acme",
        base_url="https://acme.example",
        participant_did="did:web:acme.example",
    )
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:assigner"]["@id"] == "did:web:acme.example"


def test_participant_did_override_is_the_fallback_not_an_owner_override():
    """An owner DID still wins over the participant DID."""
    mapper = GovernanceMapper(
        participant_id="acme",
        base_url="https://acme.example",
        participant_did="did:web:acme.example",
        owner_did_resolver=lambda name: "did:web:owner.example",
    )
    rule = _rule(
        access_level="open",
        classification="green",
        ownership=[GovernanceOwner(name="Someone")],
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:assigner"]["@id"] == "did:web:owner.example"


def test_participant_did_defaults_to_legacy_dev_domain():
    """Backward compatibility: omitting participant_did keeps the old value."""
    mapper = GovernanceMapper(participant_id="acme", base_url="https://acme.example")
    assert mapper.participant_did == "did:web:acme.dataspaces.localhost"
