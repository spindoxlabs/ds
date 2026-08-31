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
    PolicyObligations,
    PurposeConcept,
)

PARTICIPANT = "provider"
BASE_URL = "https://rec.dataspaces.localhost"

# Default profile for assertions
_P = OdrlProfile()

# Energy-domain profile used by tests that exercise purpose declarations
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


def _policy(**kwargs) -> DataspacePolicy:
    return DataspacePolicy(**kwargs)


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


@pytest.mark.rule("C-5")
def test_odrl_offer_basic_structure():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    offer = mapper.to_odrl_offer("datasets.gold.meters", rule)

    assert offer["@type"] == "odrl:Offer"
    assert "provider" in offer["@id"]
    assert "odrl:permission" in offer
    assert "odrl:prohibition" in offer
    assert "odrl:obligation" in offer


@pytest.mark.rule("C-5", "M-3")
def test_odrl_context_uses_profile_prefix():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    ctx = offer["@context"]
    assert ctx[_P.prefix] == _P.namespace
    assert "odrl" in ctx


@pytest.mark.rule("A-10")
def test_open_level_permits_transfer():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    actions = [p["odrl:action"]["@id"] for p in offer["odrl:permission"]]
    assert "odrl:transfer" in actions
    assert _P.term(_P.query_action) in actions


@pytest.mark.rule("A-10")
def test_restricted_level_only_query():
    mapper = _mapper()
    rule = _rule(access_level="restricted", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    actions = [p["odrl:action"]["@id"] for p in offer["odrl:permission"]]
    assert actions == [_P.term(_P.query_action)]


@pytest.mark.rule("A-6")
def test_secret_level_no_permissions():
    mapper = _mapper()
    rule = _rule(access_level="secret", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:permission"] == []


@pytest.mark.rule("A-7", "A-10")
def test_pii_prohibits_transfer_and_sublicense():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="pii")
    offer = mapper.to_odrl_offer("ds", rule)

    prohibited_actions = [p["odrl:action"]["@id"] for p in offer["odrl:prohibition"]]
    assert "odrl:transfer" in prohibited_actions
    assert "odrl:sublicense" in prohibited_actions


def _purpose_constraints(offer) -> list[dict]:
    """Every atomic purpose constraint, including those nested in an ``odrl:or``.

    Several purposes are emitted as a disjunction of ``isA`` constraints rather
    than one ``isAnyOf`` with a multi-valued operand, because EDC cannot
    serialise a multi-valued right operand — see ``GovernanceMapper``.
    """
    out: list[dict] = []
    for permission in offer["odrl:permission"]:
        for constraint in permission.get("odrl:constraint", []):
            for candidate in constraint.get("odrl:or", [constraint]):
                if candidate.get("odrl:leftOperand", {}).get("@id") == "odrl:purpose":
                    out.append(candidate)
    return out


def _purpose_iris(offer) -> list[str]:
    """Flatten purpose IRIs across constraints, whatever shape declares them."""
    iris: list[str] = []
    for constraint in _purpose_constraints(offer):
        right = constraint["odrl:rightOperand"]
        for item in right if isinstance(right, list) else [right]:
            iris.append(item["@id"])
    return iris


@pytest.mark.rule("C-6")
def test_purpose_comes_from_policy_declaration():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        policy=_policy(purpose=["GridMonitoring"]),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert any("GridMonitoring" in iri for iri in _purpose_iris(offer))


def test_purpose_uses_profile_namespace():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        policy=_policy(purpose=["GridMonitoring"]),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    iris = _purpose_iris(offer)
    assert iris
    assert all(iri.startswith(_P.namespace) for iri in iris)


@pytest.mark.rule("C-6")
def test_tags_alone_produce_no_purpose_constraint():
    """`tags` are DCAT-AP keywords — a topic is not a reason for processing."""
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(access_level="open", classification="green", tags=["grid", "rec"])
    offer = mapper.to_odrl_offer("ds", rule)
    assert _purpose_iris(offer) == []


@pytest.mark.rule("D-10")
def test_unknown_declared_purpose_is_dropped():
    """A typo must not become an unconstrained offer — it is dropped and flagged
    by the `purpose-declared` compliance check, never silently widened."""
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        policy=_policy(purpose=["GridMonitoring", "NotAPurpose"]),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert _purpose_iris(offer) == [_P.purpose_iri("GridMonitoring")] * len(
        offer["odrl:permission"]
    )


def test_declared_purpose_accepts_full_iri():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        policy=_policy(purpose=[_P.purpose_iri("GridMonitoring")]),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert _P.purpose_iri("GridMonitoring") in _purpose_iris(offer)


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
    rule = _rule(
        access_level="restricted", classification="pii", user_filter_column="sub"
    )
    offer = mapper.to_odrl_offer("ds", rule)

    consent_operand = _P.term(_P.consent_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        consent_constraints = [
            c
            for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == consent_operand
        ]
        assert len(consent_constraints) == 1
        assert consent_constraints[0]["odrl:rightOperand"]["@value"] == "active"


@pytest.mark.rule("A-8")
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


@pytest.mark.rule("A-8")
def test_attribution_obligation_uses_attribute_to():
    mapper = _mapper()
    rule = _rule(
        access_level="open",
        classification="green",
        attribution="https://provider.example/credit",
        policy=DataspacePolicy(obligations=PolicyObligations(attribution=True)),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    obligations = offer["odrl:obligation"]
    attr_obs = [o for o in obligations if o["odrl:action"]["@id"] == "odrl:attributeTo"]
    assert len(attr_obs) == 1
    assert "odrl:attributeTo" in attr_obs[0]


# ── access_requirements → constraints ────────────────────────────────────────


@pytest.mark.rule("C-21")
def test_access_requirements_all_no_membership_constraint():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", access_requirements="all")
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [
            c
            for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == membership_operand
        ]
        assert len(membership) == 0


@pytest.mark.rule("C-21")
def test_access_requirements_partner_adds_membership_constraint():
    mapper = _mapper()
    rule = _rule(
        access_level="open", classification="green", access_requirements="partner"
    )
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [
            c
            for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == membership_operand
        ]
        assert len(membership) == 1


def test_access_requirements_contract_adds_membership_and_contract():
    mapper = _mapper()
    rule = _rule(
        access_level="open", classification="green", access_requirements="contract"
    )
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [
            c
            for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == membership_operand
        ]
        contract = [
            c
            for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == "ds:contractRequired"
        ]
        assert len(membership) == 1
        assert len(contract) == 1
        # Typed, like every sibling constraint (`GOV-11`) — it was the one bare
        # literal this mapper emitted. `ContractRequiredFunction.asBoolean`
        # reaches `@value` through `Purposes.unwrapScalar`, which is the same
        # unwrapping EDC's own expansion already required.
        assert contract[0]["odrl:rightOperand"] == {
            "@value": "true",
            "@type": "xsd:boolean",
        }


def test_access_requirements_contract_does_not_emit_odrl_industry():
    """`odrl:industry eq "contract-agreed"` is not how this is said.

    It duplicated `ds:contractRequired` under an operand that means the industry
    *sector*, and nothing in `services/edc-extensions` bound it — so it was
    published to counterparties and then deleted by EDC's ScopeFilter before
    evaluation. A term that is offered and never enforced is a DSSC-AUP-06
    violation, not a harmless extra.
    """
    mapper = _mapper()
    rule = _rule(
        access_level="open", classification="green", access_requirements="contract"
    )
    offer = mapper.to_odrl_offer("ds", rule)

    operands = {
        c.get("odrl:leftOperand", {}).get("@id")
        for perm in offer["odrl:permission"]
        for c in perm.get("odrl:constraint", [])
    }
    assert "odrl:industry" not in operands


@pytest.mark.rule("C-21")
def test_internal_access_level_adds_membership_even_without_access_requirements():
    mapper = _mapper()
    rule = _rule(access_level="internal", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)

    membership_operand = _P.term(_P.membership_operand)
    for perm in offer["odrl:permission"]:
        constraints = perm.get("odrl:constraint", [])
        membership = [
            c
            for c in constraints
            if c.get("odrl:leftOperand", {}).get("@id") == membership_operand
        ]
        assert len(membership) == 1


# ── Owner DID resolution ─────────────────────────────────────────────────────


def test_assigner_uses_owner_did_when_resolver_provided():
    did = "did:web:example-org.dataspaces.localhost"
    mapper = _mapper(
        owner_did_resolver=lambda name: did if name == "example-org" else None
    )
    rule = _rule(
        access_level="open",
        classification="green",
        ownership=[GovernanceOwner(name="example-org")],
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
    assert (
        offer["odrl:assigner"]["@id"] == f"did:web:{PARTICIPANT}.dataspaces.localhost"
    )


def test_assigner_default_without_resolver():
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    assert (
        offer["odrl:assigner"]["@id"] == f"did:web:{PARTICIPANT}.dataspaces.localhost"
    )


# ── Owner-relative scope generation ─────────────────────────────────────────


def _membership_scope_values(offer: dict) -> list[str]:
    """Extract all membership right-operand values across permissions."""
    values = []
    for perm in offer.get("odrl:permission", []):
        for c in perm.get("odrl:constraint", []):
            if _left_op(c) == _P.term(_P.membership_operand):
                values.append(c["odrl:rightOperand"]["@value"])
    return values


@pytest.mark.rule("C-21")
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


@pytest.mark.rule("C-21")
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
            assert isinstance(c["odrl:leftOperand"], dict), (
                f"leftOperand not wrapped: {c}"
            )
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


@pytest.mark.rule("M-3")
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
        "datasets.gold.meters",
        rule,
        policy_id="meters-policy",
        asset_id="https://provider.example/datasets/meters",
    )
    assert contract["@type"] == "ContractDefinition"
    assert len(contract["assetsSelector"]) == 1
    assert (
        contract["assetsSelector"][0]["operandRight"]
        == "https://provider.example/datasets/meters"
    )


# ── Purpose derivation ────────────────────────────────────────────────────────


@pytest.mark.rule("A-10")
def test_several_purposes_stay_one_multi_valued_isanyof():
    """Do not replace this with a disjunction of scalar `isA` constraints.

    EDC 0.16.0 cannot serialise a multi-valued right operand — it renders it with
    `toString()` on the way out, so purposes reach every other participant as a
    Java object dump. The obvious fix, `odrl:or` of scalar `isA`, was tried
    against a running EDC and is worse: the OrConstraint is accepted on ingest and
    then fails JSON-LD compaction (`IRI_CONFUSED_WITH_PREFIX`), which 500s the
    whole Management API list response and leaves the DSP catalogue empty.

    Unreadable purposes beat no catalogue, so the multi-valued operand stays and
    this test pins it. `docs/rulebook/policies.md` carries the account of the
    profile; the packaging guard that keeps the forked transformer in the shadow
    JAR lives in `services/edc-extensions`.
    """
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        policy=_policy(purpose=["EnergyBalancing", "GridMonitoring"]),
    )
    offer = mapper.to_odrl_offer("ds", rule)

    for permission in offer["odrl:permission"]:
        assert not [c for c in permission["odrl:constraint"] if "odrl:or" in c], (
            "a disjunction breaks EDC serialisation — see the docstring"
        )
    for constraint in _purpose_constraints(offer):
        assert constraint["odrl:operator"]["@id"] == "odrl:isAnyOf"
        assert isinstance(constraint["odrl:rightOperand"], list)


def test_multiple_declared_purposes_are_deduplicated():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        # slug and full IRI of the same concept, plus a second concept
        policy=_policy(
            purpose=[
                "EnergyBalancing",
                _P.purpose_iri("EnergyBalancing"),
                "GridMonitoring",
            ]
        ),
    )
    offer = mapper.to_odrl_offer("ds", rule)

    purpose_values = _purpose_iris(offer)
    assert _P.purpose_iri("EnergyBalancing") in purpose_values
    assert _P.purpose_iri("GridMonitoring") in purpose_values
    # The slug and the full IRI denote the same concept — listed once.
    assert purpose_values.count(_P.purpose_iri("EnergyBalancing")) == len(
        offer["odrl:permission"]
    )

    # Several purposes collapse into ONE isAnyOf constraint per permission:
    # constraints inside a permission are ANDed, so one per purpose would
    # require a consumer's use to serve all of them simultaneously.
    for constraint in _purpose_constraints(offer):
        assert constraint["odrl:operator"]["@id"] == "odrl:isAnyOf"
        assert isinstance(constraint["odrl:rightOperand"], list)
    assert len(_purpose_constraints(offer)) == len(offer["odrl:permission"])


@pytest.mark.rule("A-1")
def test_single_declared_purpose_uses_is_a():
    mapper = _mapper(profile=_ENERGY_PROFILE)
    rule = _rule(
        access_level="open",
        classification="green",
        policy=_policy(purpose=["GridMonitoring"]),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    for constraint in _purpose_constraints(offer):
        assert constraint["odrl:operator"]["@id"] == "odrl:isA"
        assert constraint["odrl:rightOperand"] == {
            "@id": _P.purpose_iri("GridMonitoring")
        }


@pytest.mark.rule("C-6")
def test_tags_never_become_purposes(_p=_ENERGY_PROFILE):
    """`GOV-15` — the tag→purpose helper is gone, and the rule it broke is not.

    This asserted that `derive_purposes_from_tags` produced slugs. The helper was
    called by nothing, here or in any sibling checkout, and it stood next to the
    emitter implying a supported conversion — against the unit's own rule that
    *purposes are declared, never derived from tags*.

    What replaces it is the assertion that matters: tags the profile knows how to
    map are present on the rule, and the offer still carries **no** purpose
    constraint, because `policy.purpose[]` is empty. A dataset gets a purpose
    because someone declared a reason for processing, never because it was
    tagged.
    """
    mapper = _mapper(profile=_ENERGY_PROFILE)
    assert not hasattr(mapper, "derive_purposes_from_tags")

    rule = _rule(
        access_level="open",
        classification="green",
        tags=["rec", "grid", "meters"],
        policy=_policy(purpose=[]),
    )
    offer = mapper.to_odrl_offer("ds", rule)
    assert _purpose_constraints(offer) == []


@pytest.mark.rule("M-2")
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
        assert asset["properties"][f"{_P.prefix}:medallion"] == expected, (
            f"failed for {key}"
        )


# ── OdrlProfile model ────────────────────────────────────────────────────────


def test_profile_defaults_produce_valid_iris():
    p = OdrlProfile()
    assert p.term("Membership") == "https://w3id.org/dsp/policy/Membership"
    assert (
        p.purpose_iri("EnergyBalancing")
        == "https://w3id.org/dsp/policy/purpose/EnergyBalancing"
    )


def test_profile_custom_namespace():
    p = OdrlProfile(namespace="https://example.org/policy/", prefix="ex")
    assert p.term("Membership") == "https://example.org/policy/Membership"
    assert p.purpose_iri("Test") == "https://example.org/policy/purpose/Test"


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
    mfg_profile.purposes = [
        PurposeConcept(slug="QualityAssurance", label="Quality Assurance"),
        PurposeConcept(slug="SupplyChain", label="Supply Chain"),
        PurposeConcept(slug="PredictiveMaintenance", label="Predictive Maintenance"),
    ]
    mapper = _mapper(profile=mfg_profile)
    rule = _rule(
        access_level="internal",
        classification="green",
        tags=["quality", "logistics"],
        policy=_policy(purpose=["QualityAssurance", "SupplyChain"]),
    )
    offer = mapper.to_odrl_offer("ds", rule)

    ctx = offer["@context"]
    assert ctx["mfg-policy"] == "https://example.org/manufacturing/policy/"

    purpose_iris = _purpose_iris(offer)
    assert (
        "https://example.org/manufacturing/policy/purpose/QualityAssurance"
        in purpose_iris
    )
    assert (
        "https://example.org/manufacturing/policy/purpose/SupplyChain" in purpose_iris
    )


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


# ── `dct:conformsTo` on the EDC asset ─────────────────────────────────────────
#
# The declared payload semantic model has to survive into the DSP catalogue, or a
# consumer only learns what a dataset's columns mean after negotiating for it.


def _rule_with_conforms_to(iri):
    from ds.governance.models import DcatSpec, GovernanceRuleV2

    return GovernanceRuleV2(title="Meters", dcat=DcatSpec(conforms_to=iri))


@pytest.mark.rule("M-4")
def test_asset_carries_the_declared_semantic_model():
    mapper = GovernanceMapper(participant_id="p", base_url="https://p.example.org")
    asset = mapper.to_asset_create(
        "datasets.silver.meters",
        _rule_with_conforms_to("https://saref.etsi.org/saref4ener/"),
    )
    assert asset["properties"]["dct:conformsTo"] == "https://saref.etsi.org/saref4ener/"


def test_the_dct_prefix_is_declared_when_it_is_used():
    """EDC compacts against the context it is given.

    An emitted `dct:conformsTo` with no `dct` in the `@context` is not a DCAT-AP
    term — it is an opaque string that happens to contain a colon.
    """
    mapper = GovernanceMapper(participant_id="p", base_url="https://p.example.org")
    asset = mapper.to_asset_create(
        "datasets.silver.meters",
        _rule_with_conforms_to("https://saref.etsi.org/saref4ener/"),
    )
    assert asset["@context"]["dct"] == "http://purl.org/dc/terms/"


def test_the_dct_prefix_is_absent_when_nothing_uses_it():
    """A context prefix an asset never references claims a vocabulary it does not speak."""
    from ds.governance.models import GovernanceRuleV2

    mapper = GovernanceMapper(participant_id="p", base_url="https://p.example.org")
    asset = mapper.to_asset_create(
        "datasets.silver.meters", GovernanceRuleV2(title="M")
    )
    assert "dct" not in asset["@context"]
    assert asset["properties"]["dct:conformsTo"] is None


@pytest.mark.rule("M-4")
def test_the_semantic_model_is_not_respelled_under_the_profile_prefix():
    """`dct:conformsTo` is a DCAT-AP term, not a local one.

    Spelling it `{prefix}:conformsTo` would make a private property that merely
    looks standard — readable only by something that already knows this
    dataspace's profile, which is the opposite of why it is published.
    """
    from ds.governance.models import OdrlProfile

    profile = OdrlProfile(namespace="https://example.test/p/", prefix="ex-policy")
    mapper = GovernanceMapper(
        participant_id="p", base_url="https://p.example.org", profile=profile
    )
    asset = mapper.to_asset_create(
        "datasets.silver.meters",
        _rule_with_conforms_to("https://saref.etsi.org/saref4ener/"),
    )
    assert "ex-policy:conformsTo" not in asset["properties"]
    assert asset["properties"]["dct:conformsTo"] == "https://saref.etsi.org/saref4ener/"


# ── GOV-10 · the emitted @context declares what the document uses ────────────


@pytest.mark.rule("A-8")
def test_rdf_is_declared_when_an_obligation_uses_it():
    """A delete obligation carries `rdf:value`, so `rdf:` must be defined.

    Undeclared, `rdf:value` is not a compact IRI at all — a consumer's policy
    tooling either drops the term or keeps an unresolvable string, and either
    way the obligation this dataspace published does not mean what it says.
    """
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green", retention_days=30)
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:obligation"], "expected a delete obligation for retention_days"
    assert offer["@context"]["rdf"] == "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


@pytest.mark.rule("A-8")
def test_rdf_is_not_declared_when_nothing_uses_it():
    """Same rule as `dct` on the asset: a prefix a document never references is
    a claim about vocabularies it does not speak."""
    mapper = _mapper()
    rule = _rule(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    assert offer["odrl:obligation"] == []
    assert "rdf" not in offer["@context"]


def test_the_contract_operand_is_still_the_string_edc_binds():
    """`GOV-10`'s open half, pinned so it cannot be closed by accident.

    `services/edc-extensions` binds the **literal** `"ds:contractRequired"`.
    Declaring `ds:` in the context would make EDC expand the term, the binding
    would stop matching, and the constraint would silently stop being evaluated
    — a policy term shown and not enforced, which is what `GOV-04` was.

    So this asserts both halves together: the token is unchanged **and** the
    prefix stays undeclared. Closing the row means changing the Java binding and
    this test in the same commit, and proving it on a running exchange.
    """
    mapper = _mapper()
    rule = _rule(access_level="restricted", classification="green")
    offer = mapper.to_odrl_offer("ds", rule)
    operands = [
        c["odrl:leftOperand"]["@id"]
        for perm in offer["odrl:permission"]
        for c in perm.get("odrl:constraint", [])
    ]
    assert "ds:contractRequired" in operands
    assert "ds" not in offer["@context"]
