"""Tests for the consent-vocabulary gate.

Every failure here is a case where a person would have been shown a promise the
platform could not enforce, so each test names the specific link that broke
between the purpose taxonomy, the datasets and the offers.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ds.governance.compliance import ValidationResult, validate
from ds.governance.models import DpvMapping, OdrlProfile, PurposeConcept
from ds.governance.owners import OwnerEntry, OwnersRegistry

PARTICIPANT = "provider"
BASE_URL = "https://provider.example.org"

PROFILE = OdrlProfile(
    purposes=[
        PurposeConcept(
            slug="EnergyCommunityOperation",
            label="Energy community operation",
            definition="Operating a renewable energy community.",
        ),
        PurposeConcept(
            slug="FlexibilityResearch",
            label="Flexibility research",
            definition="Studying when consumption can shift.",
            broader="EnergyCommunityOperation",
            dpv_mapping=DpvMapping(iri="https://w3id.org/dpv#ResearchAndDevelopment"),
        ),
        PurposeConcept(
            slug="GridMonitoring",
            label="Grid monitoring",
            definition="Monitoring grid stability.",
        ),
    ]
)

OWNERS = OwnersRegistry([
    OwnerEntry(id="example-org", name="Example Org", did="did:web:example.org"),
])
ROLES = {"did:web:example.org": ["provider", "community-operator"]}


def codes(findings) -> set[str]:
    return {finding.check for finding in findings}


def write(tmp_path: Path, name: str, config: dict) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def dataset(**overrides) -> dict:
    rule = {
        "access_level": "open",
        "classification": "green",
        "policy": {"purpose": ["FlexibilityResearch"]},
        "dataspace": {
            "expose": True,
            "data_address": {"base_url": "http://dataset-api:30002"},
        },
    }
    rule.update(overrides)
    return rule


def offer(**overrides) -> dict:
    entry = {
        "id": "household-energy-flexibility",
        "purpose": "FlexibilityResearch",
        "legal_basis": "https://w3id.org/dpv#Consent",
        "datasets": ["datasets.silver.meters_15m"],
        "recipients": {
            "controller": "example-org",
            "processors": {
                "category": "appointed-service-providers",
                "admitted_by": [{"membership": "example-org"}],
            },
        },
        "measures": ["consumption"],
        "resolution": "PT15M",
        "consent_text_version": "1.0",
    }
    entry.update(overrides)
    return entry


def run(
    tmp_path: Path,
    *,
    sources: dict | None = None,
    offers: list[dict] | None = None,
    profile: OdrlProfile | None = PROFILE,
    owners: OwnersRegistry | None = OWNERS,
    roles: dict | None = None,
) -> ValidationResult:
    gov = write(
        tmp_path,
        "governance.yaml",
        {"sources": sources if sources is not None else {"datasets.silver.meters_15m": dataset()}},
    )
    offers_path = None
    if offers is not None:
        offers_path = write(tmp_path, "sharing-offers.yaml", {"sharing_offers": offers})
    return validate(
        gov,
        participant_id=PARTICIPANT,
        base_url=BASE_URL,
        profile=profile,
        owners=owners,
        sharing_offers_path=offers_path,
        participant_roles=roles if roles is not None else ROLES,
    )


# ── Purpose taxonomy ─────────────────────────────────────────────────────────

class TestPurposeTaxonomy:
    def test_valid_taxonomy_passes(self, tmp_path: Path):
        result = run(tmp_path)
        assert "purpose-hierarchy" not in codes(result.errors)
        assert "purpose-mapping" not in codes(result.errors)

    def test_unresolvable_broader_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(slug="A", label="A", definition="a", broader="Ghost"),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-hierarchy" in codes(result.errors)

    def test_broader_cycle_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(slug="A", label="A", definition="a", broader="B"),
            PurposeConcept(slug="B", label="B", definition="b", broader="A"),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-hierarchy" in codes(result.errors)

    def test_unknown_skos_relation_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(
                slug="A", label="A", definition="a",
                dpv_mapping=DpvMapping(iri="https://w3id.org/dpv#Thing", relation="sameAs"),
            ),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-mapping" in codes(result.errors)

    def test_non_iri_mapping_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(
                slug="A", label="A", definition="a",
                dpv_mapping=DpvMapping(iri="dpv:Thing"),
            ),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-mapping" in codes(result.errors)

    def test_missing_english_label_is_an_error(self, tmp_path: Path):
        """A frontend with no translation must degrade to readable English,
        never to a raw slug."""
        profile = OdrlProfile(purposes=[PurposeConcept(slug="A", label="  ")])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-labels" in codes(result.errors)

    def test_missing_definition_is_a_warning(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[PurposeConcept(slug="A", label="A")])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-labels" in codes(result.warnings)


class TestDatasetPurposes:
    def test_unknown_declared_purpose_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": ["NotAPurpose"]})})
        assert "purpose-declared" in codes(result.errors)

    def test_full_iri_declaration_is_accepted(self, tmp_path: Path):
        result = run(
            tmp_path,
            sources={"d": dataset(policy={"purpose": [PROFILE.purpose_iri("GridMonitoring")]})},
        )
        assert "purpose-declared" not in codes(result.errors)


# ── Sharing offers ───────────────────────────────────────────────────────────

class TestSharingOffers:
    def test_valid_offer_passes(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer()])
        assert result.passed, result.errors
        assert result.offers_checked == 1

    def test_offer_purpose_must_exist_in_the_taxonomy(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(purpose="NotAPurpose")])
        assert "offer-purpose" in codes(result.errors)

    def test_offer_datasets_must_resolve(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(datasets=["datasets.gold.ghost"])])
        assert "offer-datasets" in codes(result.errors)

    def test_duplicate_offer_id_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(), offer()])
        assert "offer-purpose" in codes(result.errors)

    def test_pii_dataset_must_require_consent(self, tmp_path: Path):
        """An offer over PII promises a control; the dataset must enforce it."""
        result = run(
            tmp_path,
            sources={"datasets.silver.meters_15m": dataset(classification="pii")},
            offers=[offer()],
        )
        assert "offer-consent-required" in codes(result.errors)

    def test_pii_dataset_with_consent_required_passes(self, tmp_path: Path):
        result = run(
            tmp_path,
            sources={
                "datasets.silver.meters_15m": dataset(
                    classification="pii",
                    user_filter_column="sub",
                    policy={"purpose": ["FlexibilityResearch"], "consent": {"required": True}},
                )
            },
            offers=[offer()],
        )
        assert "offer-consent-required" not in codes(result.errors)

    def test_dataset_must_declare_the_offer_purpose(self, tmp_path: Path):
        """Otherwise the negotiated offer denies the very use the person agreed to."""
        result = run(
            tmp_path,
            sources={"datasets.silver.meters_15m": dataset(policy={"purpose": ["GridMonitoring"]})},
            offers=[offer()],
        )
        assert "offer-dataset-purpose" in codes(result.errors)

    def test_broader_declaration_does_not_satisfy_a_narrower_offer(self, tmp_path: Path):
        """policy.purpose[] is matched exactly — a dataset offered for the parent
        purpose has not been declared for this specific child."""
        result = run(
            tmp_path,
            sources={
                "datasets.silver.meters_15m": dataset(
                    policy={"purpose": ["EnergyCommunityOperation"]}
                )
            },
            offers=[offer()],
        )
        assert "offer-dataset-purpose" in codes(result.errors)

    def test_unknown_controller_is_an_error(self, tmp_path: Path):
        broken = offer()
        broken["recipients"] = {**broken["recipients"], "controller": "ghost-org"}
        result = run(tmp_path, offers=[broken])
        assert "offer-controller" in codes(result.errors)

    def test_controller_role_must_be_declared_by_the_participant(self, tmp_path: Path):
        broken = offer()
        broken["recipients"] = {**broken["recipients"], "controller_role": "metering"}
        result = run(tmp_path, offers=[broken])
        assert "offer-controller" in codes(result.errors)

    def test_declared_controller_role_passes(self, tmp_path: Path):
        ok = offer()
        ok["recipients"] = {**ok["recipients"], "controller_role": "community-operator"}
        result = run(tmp_path, offers=[ok])
        assert "offer-controller" not in codes(result.errors)

    def test_controller_not_checked_without_a_registry(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer()], owners=None)
        assert "offer-controller" not in codes(result.errors)
        assert "offer-controller" in codes(result.warnings)

    def test_unknown_legal_basis_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(legal_basis="https://example.org#Vibes")])
        assert "offer-legal-basis" in codes(result.errors)

    def test_non_consent_basis_marked_revocable_is_a_warning(self, tmp_path: Path):
        result = run(
            tmp_path,
            offers=[offer(legal_basis="https://w3id.org/dpv#Contract", revocable=True)],
        )
        assert "offer-legal-basis" in codes(result.warnings)

    def test_malformed_duration_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(resolution="every 15 minutes")])
        assert "offer-durations" in codes(result.errors)

    def test_malformed_coverage_duration_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(coverage={"retrospective": "1 year"})])
        assert "offer-durations" in codes(result.errors)

    def test_unknown_subject_scope_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(subject_scope="everyone")])
        assert "offer-codes" in codes(result.errors)

    def test_empty_processor_category_is_an_error(self, tmp_path: Path):
        broken = offer()
        broken["recipients"] = {
            **broken["recipients"],
            "processors": {"category": "   ", "admitted_by": []},
        }
        result = run(tmp_path, offers=[broken])
        assert "offer-codes" in codes(result.errors)

    def test_uncheckable_processor_category_is_a_warning(self, tmp_path: Path):
        loose = offer()
        loose["recipients"] = {
            **loose["recipients"],
            "processors": {"category": "appointed-service-providers"},
        }
        result = run(tmp_path, offers=[loose])
        assert "offer-codes" in codes(result.warnings)

    def test_missing_consent_text_version_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(consent_text_version="")])
        assert "offer-codes" in codes(result.errors)

    def test_offer_with_no_datasets_is_a_warning(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(datasets=[])])
        assert "offer-datasets" in codes(result.warnings)

    def test_no_offers_file_skips_offer_checks(self, tmp_path: Path):
        result = run(tmp_path)
        assert result.offers_checked == 0
        assert not codes(result.errors) & {"offer-purpose", "offer-datasets"}
