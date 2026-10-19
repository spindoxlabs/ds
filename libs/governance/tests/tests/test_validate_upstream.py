"""`ds-governance validate` runs the platform's rules first (`celine.governance.check`).

The schema with unknown keys, the two row-policy layers, the handler names and the
layer verdicts — on the file **as ds materializes it**, base plus the overlay ds
merges, and no other. Then ds's own checks. A file that does not load is reported,
never a traceback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .test_compliance_checks import codes, exposed_dataset, run, write_governance

BOTH_LAYERS = [
    {"handler": "allow_all", "binds": "person"},
    {"handler": "allow_all", "binds": "organization"},
]


def _internal(**overrides) -> dict:
    return exposed_dataset(access_level="internal", **overrides)


@pytest.mark.rule("C-22")
def test_an_undeclared_layer_is_an_error(tmp_path: Path):
    path = write_governance(tmp_path, {"sources": {"a": _internal()}})
    result = run(path)
    assert "governance-row-policy" in codes(result.errors)
    (finding,) = [e for e in result.errors if e.check == "governance-row-policy"]
    assert finding.dataset == "a"
    assert str(path) in finding.message, "names the original file, not the copy"


@pytest.mark.rule("C-22")
def test_both_layers_declared_pass(tmp_path: Path):
    path = write_governance(
        tmp_path, {"sources": {"a": _internal(row_filters=BOTH_LAYERS)}}
    )
    assert not {c for c in codes(run(path).errors) if c.startswith("governance-")}


@pytest.mark.rule("C-22")
def test_an_unknown_handler_is_an_error(tmp_path: Path):
    filters = [
        {"handler": "no_such_handler", "args": {"column": "c"}},
        {"handler": "allow_all", "binds": "organization"},
    ]
    path = write_governance(
        tmp_path, {"sources": {"a": _internal(row_filters=filters)}}
    )
    assert "governance-handler" in codes(run(path).errors)


@pytest.mark.rule("C-22")
def test_an_unknown_key_is_a_warning(tmp_path: Path):
    path = write_governance(
        tmp_path, {"sources": {"a": exposed_dataset(colour="blue")}}
    )
    result = run(path)
    assert "governance-schema" in codes(result.warnings)
    assert "governance-schema" not in codes(result.errors)


@pytest.mark.rule("C-22")
def test_consent_coherence_is_reported_once(tmp_path: Path):
    """ds's own check, which upstream's rule 5 was ported from; not repeated."""
    filters = [
        {"handler": "rec_registry", "args": {"column": "device_id"}},
        {"handler": "allow_all", "binds": "organization"},
    ]
    path = write_governance(
        tmp_path, {"sources": {"a": _internal(row_filters=filters)}}
    )
    result = run(path)
    assert "consent-coherence" in codes(result.errors)
    assert "governance-consent-coherence" not in codes(result.errors)


@pytest.mark.rule("C-22")
def test_the_overlay_ds_merges_is_the_one_checked(tmp_path: Path):
    """The overlay completes the row policy: checked materialized, it passes."""
    path = write_governance(tmp_path, {"sources": {"a": _internal()}})
    (tmp_path / "governance.staging.yaml").write_text(
        yaml.safe_dump({"sources": {"a": {"row_filters": BOTH_LAYERS}}}),
        encoding="utf-8",
    )
    assert "governance-row-policy" in codes(run(path).errors)
    assert "governance-row-policy" not in codes(
        run(path, overlay_name="staging").errors
    )


@pytest.mark.rule("C-22")
def test_a_neighbour_named_after_the_directory_is_not_merged(tmp_path: Path):
    """Upstream infers an overlay from the directory name; ds never does."""
    directory = tmp_path / "staging"
    directory.mkdir()
    path = write_governance(directory, {"sources": {"a": _internal()}})
    (directory / "governance.staging.yaml").write_text(
        yaml.safe_dump({"sources": {"a": {"row_filters": BOTH_LAYERS}}}),
        encoding="utf-8",
    )
    assert "governance-row-policy" in codes(run(path).errors)


@pytest.mark.rule("C-10b")
def test_a_malformed_row_filter_is_reported_not_raised(tmp_path: Path):
    path = write_governance(
        tmp_path,
        {"sources": {"a": _internal(row_filters=[{"handler": "rec_registry"}])}},
    )
    result = run(path)
    assert not result.passed
    (finding,) = [e for e in result.errors if e.check == "governance-file"]
    assert "binds a person and declares no args" in finding.message
