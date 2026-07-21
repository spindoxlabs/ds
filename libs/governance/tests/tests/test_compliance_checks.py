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


def write_governance(tmp_path: Path, config: dict, name: str = "governance.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def exposed_dataset(**overrides) -> dict:
    """A minimal, valid, exposed dataset rule."""
    rule = {
        "access_level": "open",
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
    def test_missing_file_is_an_error(self, tmp_path: Path):
        result = run(tmp_path / "absent.yaml")
        assert not result.passed
        assert codes(result.errors) == {"governance-file"}

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

    def test_secret_datasets_are_not_exposed(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(access_level="secret")}},
        )
        result = run(path)
        assert result.datasets_checked == 0

    def test_valid_file_passes_cleanly(self, tmp_path: Path):
        path = write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        result = run(path)
        assert result.passed
        assert result.datasets_checked == 1
        assert result.errors == []


class TestEnums:
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
    def test_keys_differing_only_by_separator_collide(self, tmp_path: Path):
        """'a.b' and 'a-b' both derive the policy id 'a-b' — an import would clobber."""
        path = write_governance(
            tmp_path,
            {"sources": {"a.b": exposed_dataset(), "a-b": exposed_dataset()}},
        )
        result = run(path)
        assert not result.passed
        assert "policy-id-collision" in codes(result.errors)

    def test_explicit_duplicate_asset_ids_collide(self, tmp_path: Path):
        dataset = exposed_dataset()
        dataset["dataspace"]["asset"] = {"id": "urn:asset:shared"}
        path = write_governance(
            tmp_path, {"sources": {"one": dataset, "two": dataset}}
        )
        result = run(path)
        assert not result.passed
        assert "asset-id-collision" in codes(result.errors)

    def test_distinct_keys_do_not_collide(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"alpha": exposed_dataset(), "beta": exposed_dataset()}},
        )
        result = run(path)
        assert "asset-id-collision" not in codes(result.errors)
        assert "policy-id-collision" not in codes(result.errors)

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

    def test_relative_url_is_an_error(self, tmp_path: Path):
        dataset = exposed_dataset()
        dataset["dataspace"]["data_address"]["base_url"] = "/datasets/foo"
        path = write_governance(tmp_path, {"sources": {"a": dataset}})
        assert "data-address" in codes(run(path).errors)

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
    def test_consent_required_without_filter_warns(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(policy={"consent": {"required": True}})}},
        )
        result = run(path)
        assert result.passed
        assert "consent-coherence" in codes(result.warnings)

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

    def test_pii_without_row_filtering_warns(self, tmp_path: Path):
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(classification="pii")}}
        )
        assert "consent-coherence" in codes(run(path).warnings)

    def test_empty_row_filter_column_is_an_error(self, tmp_path: Path):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        row_filters=[{"handler": "by_subject", "args": {"column": "  "}}]
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

    def test_unresolvable_alias_is_an_error(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "ghost-org"}])}},
        )
        result = run(path, owners=registry)
        assert not result.passed
        assert "owner-resolvable" in codes(result.errors)

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

    def test_owner_did_not_a_participant_warns(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        result = run(path, owners=registry, participant_dids={"did:web:other.test"})
        assert "owner-participant" in codes(result.warnings)

    def test_owner_did_registered_as_participant_is_clean(self, tmp_path: Path, registry):
        path = write_governance(
            tmp_path,
            {"sources": {"a": exposed_dataset(ownership=[{"name": "example-org"}])}},
        )
        result = run(
            path, owners=registry, participant_dids={"did:web:example-org.test"}
        )
        assert "owner-participant" not in codes(result.warnings)

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
        assert run(tmp_path / "governance.yaml", overlay_name="prod").datasets_checked == 2

    def test_missing_overlay_falls_back_to_base(self, tmp_path: Path):
        path = write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        assert run(path, overlay_name="absent").datasets_checked == 1

    @pytest.mark.xfail(
        reason="GovernanceResolver._merge treats an overlay 'dataspace' block equal to "
        "the model defaults as unset, and expose:false IS the default — so an overlay "
        "cannot un-expose a dataset. Use access_level:secret instead.",
        strict=True,
    )
    def test_overlay_cannot_unexpose_via_expose_false(self, tmp_path: Path):
        write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
        write_governance(
            tmp_path,
            {"sources": {"a": {"dataspace": {"expose": False}}}},
            name="governance.prod.yaml",
        )
        assert run(tmp_path / "governance.yaml", overlay_name="prod").datasets_checked == 0


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
