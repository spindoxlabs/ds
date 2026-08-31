"""Tests for ds.governance.compliance.checks — the pre-import validation gate.

Each test builds a minimal governance file and asserts on the specific check
it targets, so a failure names the broken rule directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ds.governance.compliance import ValidationResult, validate
from ds.governance.compliance.checks import (
    check_identifier_collisions,
    check_key_policy,
    load_exposed,
)
from ds.governance.mapper import GovernanceMapper
from ds.governance.owners import OwnerEntry, OwnersRegistry
from ds.governance.resolver import GovernanceResolver

PARTICIPANT = "provider"
BASE_URL = "https://provider.example.org"


def write_governance(
    tmp_path: Path, config: dict, name: str = "governance.yaml"
) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def exposed_dataset(**overrides) -> dict:
    """A minimal, valid, exposed dataset rule.

    `policy.purpose` is part of "minimal": an exposed dataset that declares no
    purpose is published with no purpose constraint, so `purpose-declared` now
    rejects it. Before that check covered the empty case, this fixture was
    "valid" while describing a dataset nothing would have limited the use of.

    `title` and `description` joined it for the same reason (`GOV-07`): they are
    DCAT-AP **mandatory** on a `dcat:Dataset`, and the emitter has a fallback for
    each — the dataset key for one, `""` for the other — so a file declaring
    neither publishes a structurally valid record that says nothing. Every
    governance file in this repository already declares both; it was only this
    fixture that treated them as optional.
    """
    rule = {
        "access_level": "open",
        "title": "Test dataset",
        "description": "A dataset used by the compliance-check tests.",
        "policy": {"purpose": ["GridMonitoring"]},
        "dataspace": {
            "expose": True,
            "data_address": {"base_url": "http://dataset-api:30002"},
        },
    }
    rule.update(overrides)
    return rule


def run(path: Path, **kwargs) -> ValidationResult:
    kwargs.setdefault("participant_id", PARTICIPANT)
    kwargs.setdefault("base_url", BASE_URL)
    return validate(path, **kwargs)


def codes(findings) -> set[str]:
    return {finding.check for finding in findings}


class TestGovernanceFile:
    @pytest.mark.rule("C-9")
    def test_missing_file_is_an_error(self, tmp_path: Path):
        result = run(tmp_path / "absent.yaml")
        assert not result.passed
        assert codes(result.errors) == {"governance-file"}

    @pytest.mark.rule("C-9")
    def test_no_sources_is_an_error(self, tmp_path: Path):
        path = write_governance(tmp_path, {"defaults": {"access_level": "open"}})
        result = run(path)
        assert not result.passed
        assert "declares no sources" in result.errors[0].message

    def test_nothing_exposed_warns_and_stops(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": {"dataspace": {"expose": False}}}}
        )
        result = run(path)
        assert result.passed
        assert result.datasets_checked == 0
        assert codes(result.warnings) == {"governance-file"}

    @pytest.mark.rule("A-6")
    def test_secret_datasets_are_not_exposed(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(access_level="secret")}},
        )
        result = run(path)
        assert result.datasets_checked == 0

    @pytest.mark.rule("C-9", "C-14")
    def test_valid_file_passes_cleanly(self, tmp_path: Path):
        path = write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        result = run(path)
        assert result.passed
        assert result.datasets_checked == 1
        assert result.errors == []


class TestEnums:
    @pytest.mark.rule("C-9")
    def test_unknown_access_level_is_an_error(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(access_level="public")}}
        )
        result = run(path)
        assert not result.passed
        assert "access-level" in codes(result.errors)

    @pytest.mark.parametrize("level", ["open", "internal", "restricted"])
    def test_known_access_levels_accepted(self, tmp_path: Path, level: str):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(access_level=level)}}
        )
        assert "access-level" not in codes(run(path).errors)

    def test_unknown_classification_only_warns(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(classification="purple")}}
        )
        result = run(path)
        assert result.passed
        assert "classification" in codes(result.warnings)


class TestIdentifierCollisions:
    @pytest.mark.rule("A-5")
    def test_keys_differing_only_by_separator_collide(self, tmp_path: Path):
        """'a.b' and 'a-b' both derive the policy id 'a-b' — an import would clobber."""
        path = write_governance(
            tmp_path,
            {"sources": {"a.b": exposed_dataset(), "a-b": exposed_dataset()}},
        )
        result = run(path)
        assert not result.passed
        assert "policy-id-collision" in codes(result.errors)

    @pytest.mark.rule("A-5")
    def test_explicit_duplicate_asset_ids_collide(self, tmp_path: Path):
        dataset = exposed_dataset()
        dataset["dataspace"]["asset"] = {"id": "urn:asset:shared"}
        path = write_governance(tmp_path, {"sources": {"one": dataset, "two": dataset}})
        result = run(path)
        assert not result.passed
        assert "asset-id-collision" in codes(result.errors)

    @pytest.mark.rule("A-5")
    def test_distinct_keys_do_not_collide(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"alpha": exposed_dataset(), "beta": exposed_dataset()}},
        )
        result = run(path)
        assert "asset-id-collision" not in codes(result.errors)
        assert "policy-id-collision" not in codes(result.errors)

    @pytest.mark.rule("A-5")
    def test_collision_message_names_every_offending_key(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"a.b": exposed_dataset(), "a-b": exposed_dataset()}},
        )
        result = run(path)
        message = next(
            e.message for e in result.errors if e.check == "policy-id-collision"
        )
        assert "a-b" in message and "a.b" in message

    def test_check_is_a_noop_on_empty_input(self):
        result = ValidationResult(governance_path="x")
        check_identifier_collisions(result, [])
        assert result.errors == []


class TestDataAddress:
    @pytest.mark.rule("C-9")
    def test_empty_base_url_is_an_error(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": {
                        "access_level": "open",
                        "dataspace": {
                            "expose": True,
                            "data_address": {"base_url": ""},
                        },
                    }
                }
            },
        )
        result = run(path)
        assert "data-address" in codes(result.errors)

    @pytest.mark.rule("C-9")
    def test_relative_url_is_an_error(self, tmp_path: Path):
        dataset = exposed_dataset()
        dataset["dataspace"]["data_address"]["base_url"] = "/datasets/foo"
        path = write_governance(tmp_path, {"sources": {"a": dataset}})
        assert "data-address" in codes(run(path).errors)

    @pytest.mark.rule("C-9")
    def test_non_http_scheme_is_an_error(self, tmp_path: Path):
        dataset = exposed_dataset()
        dataset["dataspace"]["data_address"]["base_url"] = "ftp://files.example.org"
        path = write_governance(tmp_path, {"sources": {"a": dataset}})
        assert "data-address" in codes(run(path).errors)

    def test_https_url_accepted(self, tmp_path: Path):
        dataset = exposed_dataset()
        dataset["dataspace"]["data_address"]["base_url"] = "https://api.example.org"
        path = write_governance(tmp_path, {"sources": {"a": dataset}})
        assert "data-address" not in codes(run(path).errors)


class TestConsentCoherence:
    @pytest.mark.rule("C-10")
    def test_consent_required_without_filter_warns(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            # `policy` replaces the fixture's block wholesale, so the purpose has
            # to be restated — without it this asserts the consent warning while
            # also tripping purpose-declared, and `passed` would be False.
            {
                "sources": {
                    "a": exposed_dataset(
                        policy={
                            "purpose": ["GridMonitoring"],
                            "consent": {"required": True},
                        }
                    )
                }
            },
        )
        result = run(path)
        assert result.passed
        assert "consent-coherence" in codes(result.warnings)

    @pytest.mark.rule("C-10")
    def test_consent_required_with_filter_column_is_clean(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        user_filter_column="subject_id",
                        policy={"consent": {"required": True}},
                    )
                }
            },
        )
        assert "consent-coherence" not in codes(run(path).warnings)

    @pytest.mark.rule("C-10")
    def test_pii_without_row_filtering_warns(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(classification="pii")}}
        )
        assert "consent-coherence" in codes(run(path).warnings)

    @pytest.mark.rule("C-9")
    def test_empty_row_filter_column_is_an_error(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        row_filters=[
                            {"handler": "by_subject", "args": {"column": "  "}}
                        ]
                    )
                }
            },
        )
        assert "consent-coherence" in codes(run(path).errors)


class TestRetention:
    @pytest.mark.parametrize("value", [0, -1])
    def test_non_positive_retention_is_an_error(self, tmp_path: Path, value: int):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(retention_days=value)}}
        )
        assert "retention" in codes(run(path).errors)

    def test_positive_retention_accepted(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(retention_days=365)}}
        )
        assert "retention" not in codes(run(path).errors)

    def test_non_positive_delete_after_days_is_an_error(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        policy={"obligations": {"delete_after_days": -5}}
                    )
                }
            },
        )
        assert "retention" in codes(run(path).errors)


class TestValidityWindow:
    def test_inverted_window_is_an_error(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        policy={"valid_from": "2026-06-01", "valid_until": "2026-01-01"}
                    )
                }
            },
        )
        assert "validity-window" in codes(run(path).errors)

    def test_ordered_window_accepted(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        policy={"valid_from": "2026-01-01", "valid_until": "2026-06-01"}
                    )
                }
            },
        )
        assert "validity-window" not in codes(run(path).errors)


class TestOwners:
    @pytest.fixture
    def registry(self) -> OwnersRegistry:
        return OwnersRegistry(
            [
                OwnerEntry(
                    id="example-org",
                    did="did:web:example-org.test",
                    aliases=["example"],
                )
            ]
        )

    @pytest.mark.rule("C-10")
    def test_unresolvable_alias_is_an_error(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "ghost-org"}])}},
        )
        result = run(path, owners=registry)
        assert not result.passed
        assert "owner-resolvable" in codes(result.errors)

    @pytest.mark.rule("C-10")
    def test_resolvable_alias_passes(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        assert run(path, owners=registry).passed

    def test_registry_alias_resolves(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example"}])}},
        )
        assert "owner-resolvable" not in codes(run(path, owners=registry).errors)

    def test_no_owner_lookup_skips_resolution(self, tmp_path: Path):
        """Without a registry the check is skipped, not silently passed as an error."""
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "ghost-org"}])}},
        )
        result = run(path, owners=None)
        assert "owner-resolvable" not in codes(result.errors)

    def test_missing_ownership_warns(self, tmp_path: Path, registry):
        path = write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        result = run(path, owners=registry)
        assert "owner-declared" in codes(result.warnings)

    @pytest.mark.rule("A-4")
    def test_owner_did_not_a_participant_warns(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        result = run(path, owners=registry, participant_dids={"did:web:other.test"})
        assert "owner-participant" in codes(result.warnings)

    @pytest.mark.rule("A-4")
    def test_an_empty_participant_set_is_not_nothing_to_compare(
        self, tmp_path: Path, registry
    ):
        """`set()` means the registry was read and has nobody enrolled.

        It used to be read the same way as `None` — *no participant list was
        asked for* — and skipped, so a reachable registry with zero participants
        reported conformity. Same shape as `CI-02` and `GOV-19`: the absent state
        and the empty state are different findings.
        """
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        result = run(path, owners=registry, participant_dids=set())
        assert "owner-participant" in codes(result.warnings)

    def test_no_participant_list_still_skips(self, tmp_path: Path, registry):
        """The other side of it: an offline run that named no seed asked for
        nothing, and must not be told its owners are unregistered."""
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        result = run(path, owners=registry, participant_dids=None)
        assert "owner-participant" not in codes(result.warnings)

    @pytest.mark.rule("A-4")
    def test_owner_did_registered_as_participant_is_clean(
        self, tmp_path: Path, registry
    ):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        result = run(
            path, owners=registry, participant_dids={"did:web:example-org.test"}
        )
        assert "owner-participant" not in codes(result.warnings)

    @pytest.mark.rule("C-10")
    def test_each_alias_reported_once(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(ownership=[{"name": "ghost"}]),
                    "b": exposed_dataset(ownership=[{"name": "ghost"}]),
                }
            },
        )
        result = run(path, owners=registry)
        assert len([e for e in result.errors if e.check == "owner-resolvable"]) == 1


class TestKeyPolicy:
    def test_denied_pattern_blocks_import(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "prod.meters": exposed_dataset(),
                    "ds_dev_sample": exposed_dataset(),
                }
            },
        )
        result = run(path, deny_key_patterns=["*dev*"])
        assert not result.passed
        assert "key-policy" in codes(result.errors)
        assert "ds_dev_sample" in result.errors[0].message
        assert "prod.meters" not in result.errors[0].message

    def test_no_patterns_means_no_restriction(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"ds_dev_sample": exposed_dataset()}}
        )
        assert run(path, deny_key_patterns=[]).passed

    def test_unexposed_denied_key_is_ignored(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"ds_dev_sample": {"dataspace": {"expose": False}}}},
        )
        assert run(path, deny_key_patterns=["*dev*"]).passed

    def test_multiple_patterns_all_applied(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"a_dev": exposed_dataset(), "b_test": exposed_dataset()}},
        )
        result = run(path, deny_key_patterns=["*dev*", "*test*"])
        assert len([e for e in result.errors if e.check == "key-policy"]) == 2

    def test_check_helper_directly(self, tmp_path: Path):
        path = write_governance(tmp_path, {"sources": {"x_dev": exposed_dataset()}})
        resolver = GovernanceResolver.from_file(path)
        mapper = GovernanceMapper(participant_id=PARTICIPANT, base_url=BASE_URL)
        result = ValidationResult(governance_path=str(path))
        check_key_policy(result, load_exposed(resolver, mapper), ["*dev*"])
        assert len(result.errors) == 1


class TestOverlay:
    def test_overlay_can_withdraw_a_dataset_via_access_level(self, tmp_path: Path):
        write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        write_governance(
            tmp_path,
            {"sources": {"a": {"access_level": "secret"}}},
            name="governance.prod.yaml",
        )
        base = tmp_path / "governance.yaml"
        assert run(base).datasets_checked == 1
        assert run(base, overlay_name="prod").datasets_checked == 0

    def test_overlay_adds_a_new_dataset(self, tmp_path: Path):
        write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        write_governance(
            tmp_path, {"sources": {"b": exposed_dataset()}}, name="governance.prod.yaml"
        )
        assert (
            run(tmp_path / "governance.yaml", overlay_name="prod").datasets_checked == 2
        )

    def test_missing_overlay_falls_back_to_base(self, tmp_path: Path):
        path = write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        assert run(path, overlay_name="absent").datasets_checked == 1

    def test_an_overlay_can_unexpose_a_dataset(self, tmp_path: Path):
        """`GOV-06`, and it was an `xfail(strict)` until 2026-08-06.

        Withdrawing a dataset in one environment is the obvious thing an overlay
        is for, and it was unexpressible: `_merge_models` dumped with
        `exclude_defaults`, `expose` defaults to `False`, so `expose: false`
        dumped to nothing and the base's `expose: true` survived. The overlay
        validated clean and the dataset stayed in the catalogue — the failure
        mode being that the *safe* instruction was the one that got lost.
        """
        write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        write_governance(
            tmp_path,
            {"sources": {"a": {"dataspace": {"expose": False}}}},
            name="governance.prod.yaml",
        )
        assert (
            run(tmp_path / "governance.yaml", overlay_name="prod").datasets_checked == 0
        )

    def test_an_overlay_that_says_nothing_still_inherits_expose(self, tmp_path: Path):
        """The other half, and the reason `exclude_unset` is not `model_dump()`.

        Silence must keep inheriting. Dumping everything would make every
        unmentioned field an override with its default value — un-exposing every
        dataset an overlay merely re-titled.
        """
        write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        write_governance(
            tmp_path,
            {"sources": {"a": {"title": "Renamed in prod"}}},
            name="governance.prod.yaml",
        )
        assert (
            run(tmp_path / "governance.yaml", overlay_name="prod").datasets_checked == 1
        )

    def test_the_tightening_rules_survive_the_unset_fix(self, tmp_path: Path):
        """The risk `GOV-06`'s fix introduced, pinned.

        `consent.required` and `contract_required` are deliberately **OR**-ed by
        `_merge_policy`: *a deployer override may tighten, never loosen*, mirroring
        `dataset-api`'s own `_merge_dataspace` so that both tools reading the same
        files reach the same conclusion. Making explicit `false` meaningful is
        exactly the change that could have turned those into "override wins" and
        let an overlay un-gate a consent-gated dataset.

        `expose` is not in that set, and should not be: withdrawing a dataset is
        the tightening direction.
        """
        from ds.governance.resolver import GovernanceResolver

        write_governance(
            tmp_path,
            {
                "sources": {
                    "a": {
                        **exposed_dataset(),
                        "policy": {
                            "consent": {"required": True},
                            "obligations": {"contract_required": True},
                        },
                    }
                }
            },
        )
        write_governance(
            tmp_path,
            {
                "sources": {
                    "a": {
                        "policy": {
                            "consent": {"required": False},
                            "obligations": {"contract_required": False},
                        }
                    }
                }
            },
            name="governance.prod.yaml",
        )
        rule = GovernanceResolver.from_file_with_override(
            tmp_path / "governance.yaml", overlay_name="prod"
        ).resolve("a")
        assert rule.policy.consent.required is True
        assert rule.policy.obligations.contract_required is True


class TestResultSerialization:
    def test_asdict_round_trips(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(access_level="bogus")}}
        )
        data = run(path).asdict()
        assert data["passed"] is False
        assert data["datasets_checked"] == 1
        assert data["governance_path"] == str(path)
        assert any(e["check"] == "access-level" for e in data["errors"])
        assert "generated_at" in data

    def test_finding_includes_dataset_when_scoped(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"mine": exposed_dataset(access_level="bogus")}}
        )
        errors = run(path).asdict()["errors"]
        assert errors[0]["dataset"] == "mine"


# ── semantic-model (`M-4`, `M-7`) ─────────────────────────────────────────────


class TestSemanticModel:
    """`dcat.conforms_to` — error on unresolvable, warn on unregistered, silent on absent.

    The three-way split is the design: `M-7` makes a bare name an error, but an
    external standard IRI is legitimate whether or not this deployment mirrors it,
    and `M-6` (the platform mandates no payload model) makes "declared nothing"
    a deployment's choice rather than a finding.
    """

    @staticmethod
    def _run(conforms_to, registry=None):
        from ds.governance.compliance.checks import (
            DatasetEvidence,
            ValidationResult,
            check_semantic_model,
        )
        from ds.governance.models import DcatSpec, GovernanceRuleV2

        rule = GovernanceRuleV2(title="M", dcat=DcatSpec(conforms_to=conforms_to))
        item = DatasetEvidence(
            key="datasets.silver.meters",
            rule=rule,
            asset_id="datasets.silver.meters",
            policy_id="datasets-silver-meters-policy",
            contract_id="datasets-silver-meters-contract",
        )
        result = ValidationResult(governance_path="x")
        check_semantic_model(result, [item], registry)
        return result

    @pytest.mark.rule("M-7")
    def test_a_bare_name_is_an_error(self):
        """`M-7` — 'saref4ener' names nothing a consumer can dereference."""
        result = self._run("saref4ener")
        assert [f.check for f in result.errors] == ["semantic-model"]
        assert "not an absolute" in result.errors[0].message

    @pytest.mark.rule("M-7")
    def test_a_urn_is_an_error(self):
        assert self._run("urn:iso:std:iec:61970").errors

    @pytest.mark.rule("M-7")
    def test_an_absolute_iri_with_no_registry_passes_silently(self):
        """`None` registry means 'do not check registration', not 'nothing registered'.

        A caller that runs no vocabulary registry must not get a warning on every
        dataset that declares a model.
        """
        result = self._run("https://saref.etsi.org/saref4ener/")
        assert not result.errors and not result.warnings

    @pytest.mark.rule("M-7")
    def test_an_unregistered_iri_warns_but_does_not_fail(self):
        """Refusing here would make a deployment mirror SAREF before naming it."""
        from ds.governance.vocabularies import VocabularyRegistry

        result = self._run("https://saref.etsi.org/saref4ener/", VocabularyRegistry())
        assert not result.errors
        assert [f.check for f in result.warnings] == ["semantic-model"]

    @pytest.mark.rule("M-7")
    def test_a_registered_iri_is_clean(self):
        from ds.governance.vocabularies import Vocabulary, VocabularyRegistry

        registry = VocabularyRegistry(
            vocabularies=[
                Vocabulary(
                    slug="saref4ener",
                    title="SAREF4ENER",
                    iri="https://saref.etsi.org/saref4ener/",
                )
            ]
        )
        result = self._run("https://saref.etsi.org/saref4ener/", registry)
        assert not result.errors and not result.warnings

    @pytest.mark.rule("M-6")
    def test_declaring_no_model_is_not_a_finding(self):
        """`M-6` — the platform ships no payload model and imposes none.

        Requiring one here would be this repository taking a decision the rulebook
        explicitly leaves to a deployment.
        """
        result = self._run(None)
        assert not result.errors and not result.warnings
