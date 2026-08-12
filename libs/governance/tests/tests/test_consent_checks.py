"""Tests for the consent-vocabulary gate.

Every failure here is a case where a person would have been shown a promise the
platform could not enforce, so each test names the specific link that broke
between the purpose taxonomy, the datasets and the offers.
"""
from __future__ import annotations

import pytest

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
# The unbundling `controller_role` is checked against is declared where the real
# files declare it — beside the offers — so it is a per-test input rather than a
# module constant. It used to be
# `ROLES = {"did:web:example.org": ["provider", "community-operator"]}`, a
# *participant roles* map mixing a DSP capacity and a controller function in one
# list, which is the confusion `GOV-20` was.


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
        # DCAT-AP mandatory on a `dcat:Dataset`, and the emitter has a fallback
        # for each, so a file omitting them publishes a valid-looking record that
        # says nothing (`GOV-07`).
        "title": "Household energy flexibility",
        "description": "A dataset used by the sharing-offer tests.",
        "policy": {"purpose": ["FlexibilityResearch"]},
        "dataspace": {
            "expose": True,
            "data_address": {"base_url": "http://dataset-api:30002"},
            # The dataset declares the offer — the direction the platform reads.
            "sharing_offers": ["household-energy-flexibility"],
        },
    }
    rule.update(overrides)
    return rule


def offer(**overrides) -> dict:
    entry = {
        "id": "household-energy-flexibility",
        "purpose": "FlexibilityResearch",
        "legal_basis": "https://w3id.org/dpv#Consent",
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
    controller_roles: dict | None = None,
) -> ValidationResult:
    gov = write(
        tmp_path,
        "governance.yaml",
        {"sources": sources if sources is not None else {"datasets.silver.meters_15m": dataset()}},
    )
    offers_path = None
    if offers is not None:
        raw: dict = {"sharing_offers": offers}
        if controller_roles is not None:
            raw["controller_roles"] = controller_roles
        offers_path = write(tmp_path, "sharing-offers.yaml", raw)
    return validate(
        gov,
        participant_id=PARTICIPANT,
        base_url=BASE_URL,
        profile=profile,
        owners=owners,
        sharing_offers_path=offers_path,
    )


# ── Purpose taxonomy ─────────────────────────────────────────────────────────

class TestPurposeTaxonomy:
    def test_valid_taxonomy_passes(self, tmp_path: Path):
        result = run(tmp_path)
        assert "purpose-hierarchy" not in codes(result.errors)
        assert "purpose-mapping" not in codes(result.errors)

    @pytest.mark.rule("A-1", "M-13")
    def test_unresolvable_broader_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(slug="A", label="A", definition="a", broader="Ghost"),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-hierarchy" in codes(result.errors)

    @pytest.mark.rule("A-1", "M-13")
    def test_broader_cycle_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(slug="A", label="A", definition="a", broader="B"),
            PurposeConcept(slug="B", label="B", definition="b", broader="A"),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-hierarchy" in codes(result.errors)

    @pytest.mark.rule("M-13")
    def test_unknown_skos_relation_is_an_error(self, tmp_path: Path):
        profile = OdrlProfile(purposes=[
            PurposeConcept(
                slug="A", label="A", definition="a",
                dpv_mapping=DpvMapping(iri="https://w3id.org/dpv#Thing", relation="sameAs"),
            ),
        ])
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})}, profile=profile)
        assert "purpose-mapping" in codes(result.errors)

    @pytest.mark.rule("M-13")
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
    @pytest.mark.rule("D-10")
    def test_unknown_declared_purpose_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": ["NotAPurpose"]})})
        assert "purpose-declared" in codes(result.errors)

    @pytest.mark.rule("D-10")
    def test_full_iri_declaration_is_accepted(self, tmp_path: Path):
        result = run(
            tmp_path,
            sources={"d": dataset(policy={"purpose": [PROFILE.purpose_iri("GridMonitoring")]})},
        )
        assert "purpose-declared" not in codes(result.errors)

    @pytest.mark.rule("C-11", "D-7")
    def test_empty_purpose_is_an_error(self, tmp_path: Path):
        """The case that used to pass: no entries, so nothing to iterate.

        The mapper emits a purpose constraint only for a non-empty list, so an
        exposed dataset declaring `purpose: []` is published with no purpose
        limitation at all — the same outcome as a typo, and previously silent.
        """
        result = run(tmp_path, sources={"d": dataset(policy={"purpose": []})})
        assert "purpose-declared" in codes(result.errors)

    @pytest.mark.rule("C-11", "D-7")
    def test_absent_purpose_block_is_an_error(self, tmp_path: Path):
        """Omitting `policy` entirely must fail the same way as declaring it empty."""
        result = run(tmp_path, sources={"d": dataset(policy={})})
        assert "purpose-declared" in codes(result.errors)

    @pytest.mark.rule("C-10")
    def test_error_names_every_unresolvable_entry(self, tmp_path: Path):
        """A producer revising a file needs the whole list, not the first item."""
        result = run(
            tmp_path,
            sources={"d": dataset(policy={"purpose": ["NotAPurpose", "AlsoWrong"]})},
        )
        messages = " ".join(f.message for f in result.errors)
        assert "NotAPurpose" in messages
        assert "AlsoWrong" in messages


# ── Sharing offers ───────────────────────────────────────────────────────────

class TestSharingOffers:
    def test_valid_offer_passes(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer()])
        assert result.passed, result.errors
        assert result.offers_checked == 1

    def test_offer_purpose_must_exist_in_the_taxonomy(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(purpose="NotAPurpose")])
        assert "offer-purpose" in codes(result.errors)

    @pytest.mark.rule("C-10")
    def test_dataset_referencing_an_unknown_offer_is_an_error(self, tmp_path: Path):
        """"No sharing offer" and "not shared" are the same statement.

        Publishing the dataset anyway would advertise a consent gate that can
        never open.
        """
        result = run(
            tmp_path,
            sources={
                "datasets.silver.meters_15m": dataset(
                    dataspace={
                        "expose": True,
                        "data_address": {"base_url": "http://dataset-api:30002"},
                        "sharing_offers": ["no-such-offer"],
                    }
                )
            },
            offers=[offer()],
        )
        assert "offer-datasets" in codes(result.errors)

    @pytest.mark.rule("C-10")
    def test_duplicate_offer_id_is_an_error(self, tmp_path: Path):
        """Reported, not raised: "which file do I fix" needs an answer."""
        result = run(tmp_path, offers=[offer(), offer()])
        assert "offer-duplicate" in codes(result.errors)
        assert not result.passed

    @pytest.mark.rule("D-11")
    def test_a_conflicting_unbundling_is_reported_as_a_controller_finding(
        self, tmp_path: Path
    ):
        """Reported, not raised, and under the right code.

        `offer-duplicate` would send a reader looking for two offers sharing an
        id. This is two files disagreeing about whether one controller is
        unbundled, which decides which consent a request can reach.
        """
        run(tmp_path, offers=[offer()], controller_roles={"example-org": ["a"]})
        contrib = tmp_path / "sharing-offers.d"
        contrib.mkdir()
        (contrib / "other.yaml").write_text(
            yaml.safe_dump({"controller_roles": {"example-org": ["b"]}}),
            encoding="utf-8",
        )

        result = run(tmp_path, offers=[offer()], controller_roles={"example-org": ["a"]})

        assert "offer-controller" in codes(result.errors)
        assert "offer-duplicate" not in codes(result.errors)
        assert not result.passed

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

    @pytest.mark.rule("C-10")
    def test_dataset_must_declare_the_offer_purpose(self, tmp_path: Path):
        """Otherwise the negotiated offer denies the very use the person agreed to."""
        result = run(
            tmp_path,
            sources={"datasets.silver.meters_15m": dataset(policy={"purpose": ["GridMonitoring"]})},
            offers=[offer()],
        )
        assert "offer-dataset-purpose" in codes(result.errors)

    @pytest.mark.rule("A-2", "D-9")
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

    @pytest.mark.rule("D-11a")
    def test_a_controller_role_with_no_declared_vocabulary_is_an_error(self, tmp_path: Path):
        """The state the whole repository was in until 2026-08-08.

        `governance-rec` declared `controller_role: operations` and no file
        anywhere said what `operations` was. The old check asked the
        identity-registry for the answer, got an empty set, and passed — so the
        one shape that must never be silent is the one that was.
        """
        broken = offer()
        broken["recipients"] = {**broken["recipients"], "controller_role": "metering"}
        result = run(tmp_path, offers=[broken])
        assert "offer-controller" in codes(result.errors)

    @pytest.mark.rule("D-11a")
    def test_a_controller_role_outside_the_declared_vocabulary_is_an_error(
        self, tmp_path: Path
    ):
        broken = offer()
        broken["recipients"] = {**broken["recipients"], "controller_role": "metering"}
        result = run(
            tmp_path,
            offers=[broken],
            controller_roles={"example-org": ["community-operator"]},
        )
        assert "offer-controller" in codes(result.errors)

    @pytest.mark.rule("D-11a")
    def test_declared_controller_role_passes(self, tmp_path: Path):
        ok = offer()
        ok["recipients"] = {**ok["recipients"], "controller_role": "community-operator"}
        result = run(
            tmp_path,
            offers=[ok],
            controller_roles={"example-org": ["community-operator", "metering"]},
        )
        assert "offer-controller" not in codes(result.errors)

    @pytest.mark.rule("D-11a", "D-11")
    def test_an_unbundled_controller_must_be_named_by_role(self, tmp_path: Path):
        """`D-11`: the consent key is (subject, purpose, controller-role).

        Declaring the entity unbundled and then omitting the function leaves the
        key one element short, and the connector matches on the legal entity —
        so a consent given to metering would be honoured for operations.
        """
        result = run(
            tmp_path,
            offers=[offer()],
            controller_roles={"example-org": ["community-operator", "metering"]},
        )
        assert "offer-controller" in codes(result.errors)

    @pytest.mark.rule("D-5")
    def test_a_controller_that_is_not_unbundled_needs_no_role(self, tmp_path: Path):
        """Most controllers are one controller. Requiring a role from all of them
        would make the ordinary case declare a distinction it does not have."""
        result = run(tmp_path, offers=[offer()])
        assert "offer-controller" not in codes(result.errors)

    def test_controller_existence_not_checked_without_a_registry(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer()], owners=None)
        assert "offer-controller" not in codes(result.errors)
        assert "offer-controller" in codes(result.warnings)

    @pytest.mark.rule("D-11a")
    def test_the_role_vocabulary_is_still_checked_without_a_registry(self, tmp_path: Path):
        """The two halves are independent, and this is the point of splitting them.

        Whether the entity exists needs a registry; whether the named function is
        one it declared does not — that answer is in the file being validated, so
        an offline run checks it in full instead of downgrading to a warning.
        """
        broken = offer()
        broken["recipients"] = {**broken["recipients"], "controller_role": "operations"}
        result = run(
            tmp_path,
            offers=[broken],
            owners=None,
            controller_roles={"example-org": ["metering"]},
        )
        assert "offer-controller" in codes(result.errors)

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

    @pytest.mark.rule("D-12", "D-13")
    def test_missing_consent_text_version_is_an_error(self, tmp_path: Path):
        result = run(tmp_path, offers=[offer(consent_text_version="")])
        assert "offer-codes" in codes(result.errors)

    def test_an_offer_no_dataset_declares_is_a_warning(self, tmp_path: Path):
        """Consenting to it would share nothing — wasteful, not unsafe."""
        result = run(tmp_path, offers=[offer(), offer(id="orphan")])
        assert "offer-datasets" in codes(result.warnings)

    def test_no_offers_file_skips_offer_checks(self, tmp_path: Path):
        result = run(tmp_path)
        assert result.offers_checked == 0
        assert not codes(result.errors) & {"offer-purpose", "offer-datasets"}
