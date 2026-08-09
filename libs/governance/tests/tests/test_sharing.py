"""Tests for the consent vocabulary — purpose hierarchy, offers, re-consent hash."""
import pytest
from pydantic import ValidationError

from ds.governance.models import (
    DpvMapping,
    OdrlProfile,
    PurposeConcept,
    load_odrl_profile,
)
from ds.governance.sharing import (
    CONSENT_BASIS,
    ConflictingControllerRolesError,
    DuplicateOfferError,
    OfferCoverage,
    OfferRecipients,
    ProcessorCategory,
    SharingOffer,
    datasets_by_offer,
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


def test_the_hash_cannot_see_datasets_at_all():
    """Schema migration and source swaps must never invalidate consent.

    This used to be a rule — the hash *excluded* `datasets`. It is now
    structural: an offer has no datasets to exclude, because the dataset names
    the offer. Nothing an operator does to the backing datasets can reach these
    bytes, so there is no longer a rule anyone can forget to apply.
    """
    facts = _offer().user_visible_facts()
    assert "datasets" not in facts
    assert not any("dataset" in key for key in facts)


def test_an_offer_declaring_datasets_is_rejected():
    """A stale file must fail, not quietly lose its datasets.

    Ignoring the key would leave the offer reaching nothing while looking
    correct — the silent half-migration this inversion exists to avoid.
    """
    with pytest.raises(ValidationError, match="datasets"):
        _offer(datasets=["datasets.silver.meters_15m"])


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
    recipients:
      controller: site-org
      processors:
        category: appointed-service-providers
    consent_text_version: "1.0"
  - id: grid-monitoring
    purpose: GridMonitoring
    legal_basis: "https://w3id.org/dpv#Consent"
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


# ── The reverse index ────────────────────────────────────────────────────────

def test_datasets_by_offer_reverses_the_declaration():
    index = datasets_by_offer({
        "datasets.silver.meters_15m": ["household-energy-flexibility", "grid-ops"],
        "datasets.gold.meters_1h": ["household-energy-flexibility"],
        "datasets.gold.grid": [],
    })
    assert index["household-energy-flexibility"] == [
        "datasets.silver.meters_15m",
        "datasets.gold.meters_1h",
    ]
    assert index["grid-ops"] == ["datasets.silver.meters_15m"]
    assert "datasets.gold.grid" not in index


def test_datasets_by_offer_is_order_stable_and_deduplicates():
    """A reordering between syncs would churn consent rows for no reason."""
    declared = {
        "datasets.a": ["offer-1", "offer-1"],
        "datasets.b": ["offer-1"],
    }
    assert datasets_by_offer(declared)["offer-1"] == ["datasets.a", "datasets.b"]
    assert datasets_by_offer(declared) == datasets_by_offer(dict(declared))


def test_an_offer_nothing_declares_simply_has_no_datasets():
    """Not an error here — the compliance gate decides what an orphan means."""
    assert datasets_by_offer({"datasets.a": []}) == {}


# ── Contributed offer files (T24 / T33) ──────────────────────────────────────

def _offer_yaml(offer_id: str, controller: str = "example-org") -> str:
    return f"""\
sharing_offers:
  - id: {offer_id}
    purpose: FlexibilityResearch
    legal_basis: "https://w3id.org/dpv#Consent"
    recipients:
      controller: {controller}
      processors:
        category: appointed-service-providers
    consent_text_version: "1.0"
"""


def _contrib(tmp_path, name: str, body: str):
    d = tmp_path / "sharing-offers.d"
    d.mkdir(exist_ok=True)
    (d / name).write_text(body)


def test_contributed_files_union_with_the_base(tmp_path):
    (tmp_path / "sharing-offers.yaml").write_text(_offer_yaml("local-offer"))
    _contrib(tmp_path, "acme.yaml", _offer_yaml("acme-flexibility"))
    _contrib(tmp_path, "beta.yaml", _offer_yaml("beta-flexibility"))

    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")

    assert {o.id for o in catalogue.offers} == {
        "local-offer", "acme-flexibility", "beta-flexibility",
    }


def test_a_contribution_needs_no_base_file(tmp_path):
    """A deployment with no offers of its own can still receive them."""
    _contrib(tmp_path, "acme.yaml", _offer_yaml("acme-flexibility"))
    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")
    assert [o.id for o in catalogue.offers] == ["acme-flexibility"]


def test_every_offer_records_which_file_declared_it(tmp_path):
    """Offers are contributed, so "who declared this" must be answerable."""
    (tmp_path / "sharing-offers.yaml").write_text(_offer_yaml("local-offer"))
    _contrib(tmp_path, "acme.yaml", _offer_yaml("acme-flexibility"))

    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")

    assert catalogue.source_of("local-offer") == "sharing-offers.yaml"
    assert catalogue.source_of("acme-flexibility") == "acme.yaml"


def test_duplicate_id_across_files_names_both(tmp_path):
    """No baseline means no winner to pick — and picking one silently would let
    one producer redefine consent text another producer's subjects agreed to."""
    (tmp_path / "sharing-offers.yaml").write_text(_offer_yaml("shared-id"))
    _contrib(tmp_path, "acme.yaml", _offer_yaml("shared-id", controller="other-org"))

    with pytest.raises(DuplicateOfferError) as exc:
        load_sharing_offers(tmp_path / "sharing-offers.yaml")

    assert "shared-id" in str(exc.value)
    assert "sharing-offers.yaml" in str(exc.value)
    assert "acme.yaml" in str(exc.value)


def test_duplicate_between_two_contributions_names_both(tmp_path):
    _contrib(tmp_path, "acme.yaml", _offer_yaml("shared-id"))
    _contrib(tmp_path, "beta.yaml", _offer_yaml("shared-id"))

    with pytest.raises(DuplicateOfferError) as exc:
        load_sharing_offers(tmp_path / "sharing-offers.yaml")

    assert "acme.yaml" in str(exc.value)
    assert "beta.yaml" in str(exc.value)


def test_collection_order_is_by_name_not_filesystem_order(tmp_path):
    """Reproducible diagnostics across machines running the same commit."""
    for name in ("zulu.yaml", "alpha.yaml", "mike.yaml"):
        _contrib(tmp_path, name, _offer_yaml(name.removesuffix(".yaml")))

    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")

    assert [o.id for o in catalogue.offers] == ["alpha", "mike", "zulu"]


def test_the_overlay_still_replaces_and_is_not_a_contribution(tmp_path):
    """`sharing-offers.<name>.yaml` is an opt-in deployment rebinding.

    It must keep replace-by-id, and must not be swept up as a contribution —
    otherwise rebinding a controller would collide with the offer it rebinds.
    """
    (tmp_path / "sharing-offers.yaml").write_text(_offer_yaml("local-offer"))
    (tmp_path / "sharing-offers.site.yaml").write_text(
        _offer_yaml("local-offer", controller="site-org")
    )

    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml", overlay_name="site")

    assert len(catalogue.offers) == 1
    assert catalogue.get("local-offer").recipients.controller == "site-org"
    assert catalogue.source_of("local-offer") == "sharing-offers.site.yaml"


# ── The controller-role vocabulary (GOV-20) ──────────────────────────────────
#
# `controller_role` was checked against the identity-registry's participant
# roles until 2026-08-08. Those are DSP capacities the registry pins to
# `{provider, consumer}`, so no legal `controller_role` could be one of them —
# the check could only pass by comparing against an empty set, which is what it
# did against every registry. The vocabulary lives here now, in the file that
# uses it.


def _roles_yaml(offer_id: str, controller: str, roles: list[str]) -> str:
    listed = ", ".join(roles)
    return _offer_yaml(offer_id, controller=controller) + (
        f"controller_roles:\n  {controller}: [{listed}]\n"
    )


def test_controller_roles_are_read_from_the_file(tmp_path):
    (tmp_path / "sharing-offers.yaml").write_text(
        _roles_yaml("local-offer", "grid-operator", ["operations", "metering"])
    )
    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")
    assert catalogue.roles_of("grid-operator") == ["metering", "operations"]


def test_a_controller_that_declares_nothing_is_not_unbundled(tmp_path):
    (tmp_path / "sharing-offers.yaml").write_text(_offer_yaml("local-offer"))
    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")
    assert catalogue.roles_of("example-org") == []


def test_declaration_order_is_not_a_different_unbundling(tmp_path):
    """Sorted on the way in, so `[a, b]` and `[b, a]` are one fact, not two.

    Without this, two producers stating the same unbundling in a different order
    would be a `ConflictingControllerRolesError`.
    """
    (tmp_path / "sharing-offers.yaml").write_text(
        _roles_yaml("local-offer", "grid-operator", ["operations", "metering"])
    )
    _contrib(
        tmp_path,
        "acme.yaml",
        _roles_yaml("acme-offer", "grid-operator", ["metering", "operations"]),
    )
    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")
    assert catalogue.roles_of("grid-operator") == ["metering", "operations"]


def test_two_files_unbundling_a_controller_differently_names_both(tmp_path):
    """Whether a controller is unbundled decides which consent a request reaches,
    so there is no winner to pick silently."""
    (tmp_path / "sharing-offers.yaml").write_text(
        _roles_yaml("local-offer", "grid-operator", ["operations"])
    )
    _contrib(
        tmp_path,
        "acme.yaml",
        _roles_yaml("acme-offer", "grid-operator", ["operations", "metering"]),
    )

    with pytest.raises(ConflictingControllerRolesError) as exc:
        load_sharing_offers(tmp_path / "sharing-offers.yaml")

    assert "grid-operator" in str(exc.value)
    assert "sharing-offers.yaml" in str(exc.value)
    assert "acme.yaml" in str(exc.value)


def test_a_contribution_may_declare_an_unbundling_the_base_does_not(tmp_path):
    (tmp_path / "sharing-offers.yaml").write_text(_offer_yaml("local-offer"))
    _contrib(
        tmp_path,
        "acme.yaml",
        _roles_yaml("acme-offer", "grid-operator", ["operations"]),
    )
    catalogue = load_sharing_offers(tmp_path / "sharing-offers.yaml")
    assert catalogue.roles_of("grid-operator") == ["operations"]


def test_the_overlay_may_rebind_an_unbundling(tmp_path):
    """Same standing as rebinding a controller alias: a deliberate deployment
    statement, not a contribution competing with one."""
    (tmp_path / "sharing-offers.yaml").write_text(
        _roles_yaml("local-offer", "grid-operator", ["operations"])
    )
    (tmp_path / "sharing-offers.site.yaml").write_text(
        _roles_yaml("local-offer", "grid-operator", ["dispatch"])
    )

    catalogue = load_sharing_offers(
        tmp_path / "sharing-offers.yaml", overlay_name="site"
    )

    assert catalogue.roles_of("grid-operator") == ["dispatch"]
