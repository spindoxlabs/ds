"""Tests for the consent vocabulary — purpose hierarchy, offers, re-consent hash."""
import pytest

from ds.governance.models import (
    DpvMapping,
    OdrlProfile,
    PurposeConcept,
    load_odrl_profile,
)
from ds.governance.sharing import (
    CONSENT_BASIS,
    OfferCoverage,
    OfferRecipients,
    ProcessorCategory,
    SharingOffer,
    is_iso_duration,
    load_sharing_offers,
)

# A three-level hierarchy: Flexibility ⊂ CommunityOperation, Grid stands alone.
_PROFILE = OdrlProfile(
    purposes=[
        PurposeConcept(slug="EnergyCommunityOperation", label="Energy community operation"),
        PurposeConcept(
            slug="FlexibilityResearch",
            label="Flexibility research",
            broader="EnergyCommunityOperation",
        ),
        PurposeConcept(
            slug="IncentiveCalculation",
            label="Incentive calculation",
            broader="EnergyCommunityOperation",
        ),
        PurposeConcept(slug="GridMonitoring", label="Grid monitoring"),
    ]
)


def _offer(**kwargs) -> SharingOffer:
    defaults = dict(
        id="household-energy-flexibility",
        purpose="FlexibilityResearch",
        legal_basis=CONSENT_BASIS,
        datasets=["datasets.silver.meters_15m"],
        recipients=OfferRecipients(
            controller="example-org",
            processors=ProcessorCategory(
                category="appointed-service-providers",
                admitted_by=[{"membership": "example-org"}],
            ),
        ),
        measures=["consumption"],
        resolution="PT15M",
        coverage=OfferCoverage(retrospective="P1Y", prospective="P2Y"),
        consent_text_version="1.0",
        retention="P2Y",
    )
    defaults.update(kwargs)
    return SharingOffer(**defaults)


# ── Purpose taxonomy ─────────────────────────────────────────────────────────

def test_broader_chain_walks_local_hierarchy():
    assert _PROFILE.broader_chain("FlexibilityResearch") == [
        "FlexibilityResearch",
        "EnergyCommunityOperation",
    ]
    assert _PROFILE.broader_chain("GridMonitoring") == ["GridMonitoring"]
    assert _PROFILE.broader_chain("NotAPurpose") == []


def test_purpose_slug_normalises_iri_and_compact_forms():
    assert _PROFILE.purpose_slug("FlexibilityResearch") == "FlexibilityResearch"
    assert _PROFILE.purpose_slug(_PROFILE.purpose_iri("FlexibilityResearch")) == "FlexibilityResearch"
    assert _PROFILE.purpose_slug("dsp-policy:purpose/FlexibilityResearch") == "FlexibilityResearch"
    assert _PROFILE.purpose_slug("purpose/FlexibilityResearch") == "FlexibilityResearch"
    assert _PROFILE.purpose_slug("SomethingElse") is None
    assert _PROFILE.purpose_slug("") is None


def test_is_a_allows_narrower_requests_only():
    # Consented to the parent → a narrower request is covered.
    assert _PROFILE.is_a("FlexibilityResearch", "EnergyCommunityOperation")
    # Same concept.
    assert _PROFILE.is_a("FlexibilityResearch", "FlexibilityResearch")
    # Consented to a child → a broader request is NOT covered.
    assert not _PROFILE.is_a("EnergyCommunityOperation", "FlexibilityResearch")
    # Siblings never match.
    assert not _PROFILE.is_a("IncentiveCalculation", "FlexibilityResearch")
    # Unrelated tree.
    assert not _PROFILE.is_a("GridMonitoring", "EnergyCommunityOperation")


def test_is_a_never_follows_dpv_mapping():
    """A broadMatch to a generic DPV term must not widen consent."""
    profile = OdrlProfile(
        purposes=[
            PurposeConcept(
                slug="FlexibilityResearch",
                label="Flexibility research",
                dpv_mapping=DpvMapping(iri="https://w3id.org/dpv#ResearchAndDevelopment"),
            ),
            PurposeConcept(
                slug="MarketResearch",
                label="Market research",
                dpv_mapping=DpvMapping(iri="https://w3id.org/dpv#ResearchAndDevelopment"),
            ),
        ]
    )
    # Both map to the same DPV term; neither may satisfy the other.
    assert not profile.is_a("MarketResearch", "FlexibilityResearch")
    assert not profile.is_a("FlexibilityResearch", "MarketResearch")


def test_broader_chain_terminates_on_a_cycle():
    profile = OdrlProfile(
        purposes=[
            PurposeConcept(slug="A", label="A", broader="B"),
            PurposeConcept(slug="B", label="B", broader="A"),
        ]
    )
    assert profile.broader_chain("A") == ["A", "B"]


def test_purpose_iris_are_not_confusable_with_a_compact_iri():
    """A `purpose:` base compacts to `purpose:Slug`, which JSON-LD rejects
    (IRI_CONFUSED_WITH_PREFIX) and which fails the whole DSP catalogue response."""
    profile = load_odrl_profile()
    relative = profile.purpose_iri("FlexibilityResearch")[len(profile.namespace):]
    assert ":" not in relative.split("/", 1)[0]


def test_shipped_energy_profile_hierarchy_and_mappings():
    profile = load_odrl_profile()
    assert profile.broader_chain("IncentiveCalculation") == [
        "IncentiveCalculation",
        "EnergyCommunityOperation",
    ]
    # Every mapping is a broadMatch: our purposes are domain specialisations of
    # DPV's generic terms, and exactMatch would silently widen consent.
    for concept in profile.purposes:
        if concept.dpv_mapping:
            assert concept.dpv_mapping.relation == "broadMatch"
            assert concept.dpv_mapping.iri.startswith("https://w3id.org/dpv#")


# ── ISO 8601 durations ───────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["P1Y", "P2Y", "PT15M", "P5Y", "P30D", "PT1H30M", "P4W"])
def test_valid_iso_durations(value):
    assert is_iso_duration(value)


@pytest.mark.parametrize("value", ["", "15m", "P", "1Y", "PT", "P1Y2W", "every 15 minutes"])
def test_invalid_iso_durations(value):
    assert not is_iso_duration(value)


# ── Offer schema ─────────────────────────────────────────────────────────────

def test_offer_round_trip():
    offer = _offer()
    restored = SharingOffer.model_validate(offer.model_dump())
    assert restored == offer


def test_only_consent_based_offers_require_a_control():
    assert _offer().requires_consent
    assert not _offer(legal_basis="https://w3id.org/dpv#Contract").requires_consent


# ── user_visible_hash — the re-consent trigger ───────────────────────────────

def _hash(offer: SharingOffer) -> str:
    slug = _PROFILE.purpose_slug(offer.purpose)
    return offer.user_visible_hash(_PROFILE.broader_chain(slug) if slug else [])


def test_hash_is_stable_across_recomputation():
    offer = _offer()
    assert _hash(offer) == _hash(_offer())


def test_hash_ignores_dataset_changes():
    """Schema migration, medallion re-layering and source swaps are invisible to
    the person, so they must not invalidate consent."""
    baseline = _hash(_offer())
    assert _hash(_offer(datasets=["datasets.gold.meters_1h"])) == baseline
    assert _hash(_offer(datasets=[])) == baseline
    assert _hash(_offer(datasets=["a", "b", "c"])) == baseline


@pytest.mark.parametrize(
    "change",
    [
        {"resolution": "PT1H"},
        {"coverage": OfferCoverage(retrospective="P5Y", prospective="P2Y")},
        {"measures": ["consumption", "production"]},
        {"retention": "P5Y"},
        {"subject_scope": "community"},
        {"legal_basis": "https://w3id.org/dpv#Contract"},
        {"revocable": False},
    ],
)
def test_hash_reacts_to_user_visible_changes(change):
    assert _hash(_offer(**change)) != _hash(_offer())


def test_hash_reacts_to_a_new_controller():
    """A different controller is a different processing operation (Art. 4(11))."""
    other = OfferRecipients(
        controller="other-org",
        processors=ProcessorCategory(
            category="appointed-service-providers",
            admitted_by=[{"membership": "example-org"}],
        ),
    )
    assert _hash(_offer(recipients=other)) != _hash(_offer())


def test_hash_reacts_to_a_controller_role_change():
    """Controller ≠ legal entity: a DSO's grid and metering roles are distinct."""
    role = OfferRecipients(
        controller="example-org",
        controller_role="metering",
        processors=ProcessorCategory(
            category="appointed-service-providers",
            admitted_by=[{"membership": "example-org"}],
        ),
    )
    assert _hash(_offer(recipients=role)) != _hash(_offer())


def test_hash_reacts_to_a_processor_category_change():
    swapped = OfferRecipients(
        controller="example-org",
        processors=ProcessorCategory(category="research-partners", admitted_by=[]),
    )
    assert _hash(_offer(recipients=swapped)) != _hash(_offer())


def test_hash_ignores_new_processors_inside_the_declared_category():
    """Same controller, same operation — disclosed and notified, never re-asked."""
    widened = OfferRecipients(
        controller="example-org",
        processors=ProcessorCategory(
            category="appointed-service-providers",
            admitted_by=[{"membership": "example-org"}, {"membership": "partner-org"}],
        ),
    )
    assert _hash(_offer(recipients=widened)) == _hash(_offer())


def test_hash_ignores_consent_text_version_bump():
    """An editorial or translation fix is recorded, not re-asked."""
    assert _hash(_offer(consent_text_version="1.1")) == _hash(_offer())


def test_hash_reacts_to_purpose_and_to_its_broader_chain():
    offer = _offer()
    baseline = _hash(offer)
    assert _hash(_offer(purpose="GridMonitoring")) != baseline
    # Re-parenting a purpose changes what the person was told, even if the
    # leaf slug is unchanged.
    assert offer.user_visible_hash(["FlexibilityResearch"]) != baseline


# ── Loading ──────────────────────────────────────────────────────────────────

_BASE_YAML = """\
sharing_offers:
  - id: household-energy-flexibility
    purpose: FlexibilityResearch
    legal_basis: "https://w3id.org/dpv#Consent"
    datasets: [datasets.silver.meters_15m]
    recipients:
      controller: example-org
      processors:
        category: appointed-service-providers
        admitted_by:
          - membership: example-org
    measures: [consumption]
    resolution: PT15M
    consent_text_version: "1.0"
"""


def test_load_offers(tmp_path):
    path = tmp_path / "sharing-offers.yaml"
    path.write_text(_BASE_YAML)
    catalogue = load_sharing_offers(path)
    assert len(catalogue.offers) == 1
    offer = catalogue.get("household-energy-flexibility")
    assert offer is not None
    assert offer.recipients.processors.admitted_by == [{"membership": "example-org"}]
    assert catalogue.for_dataset("datasets.silver.meters_15m") == [offer]
    assert catalogue.consent_based() == [offer]


def test_load_offers_missing_file_is_empty(tmp_path):
    assert load_sharing_offers(tmp_path / "nope.yaml").offers == []
    assert load_sharing_offers(None).offers == []


def test_overlay_replaces_by_id_and_appends(tmp_path):
    (tmp_path / "sharing-offers.yaml").write_text(_BASE_YAML)
    (tmp_path / "sharing-offers.site.yaml").write_text("""\
sharing_offers:
  - id: household-energy-flexibility
    purpose: FlexibilityResearch
    legal_basis: "https://w3id.org/dpv#Consent"
    datasets: [datasets.silver.meters_15m]
    recipients:
      controller: site-org
      processors:
        category: appointed-service-providers
    consent_text_version: "1.0"
  - id: grid-monitoring
    purpose: GridMonitoring
    legal_basis: "https://w3id.org/dpv#Consent"
    datasets: [datasets.silver.meters_15m]
    recipients:
      controller: dso-org
      processors:
        category: grid-operators
    consent_text_version: "1.0"
""")
    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml", overlay_name="site")
    assert len(catalogue.offers) == 2
    # Rebinding a controller for a deployment must not fork the base file.
    assert catalogue.get("household-energy-flexibility").recipients.controller == "site-org"
    assert catalogue.get("grid-monitoring") is not None
