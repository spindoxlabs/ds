"""Tests for GovernanceResolver — YAML loading, resolving, merging."""

import textwrap
from pathlib import Path

import pytest

from ds.governance.resolver import (
    GovernanceConfig,
    GovernanceResolver,
    exposed_owner_aliases,
)
from ds.governance.models import GovernanceRuleV2, DataspaceSpec


# ── helpers ───────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "governance.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ── tests ─────────────────────────────────────────────────────────────────────


def test_from_file_missing_raises(tmp_path):
    """A configured path that is missing is an error, not an empty config.

    It returned an empty config until 2026-08-07, and the cost was measurable:
    the connector's default path named a directory `245ae53` had renamed, so
    every `task dev:*` provider since ran with **no governance** — no datasets,
    no sharing offers — starting clean and logging nothing. Compose was fine, so
    nothing in CI or in a container run could see it.

    This is `CI-02`'s rule, and it is the same one `GOV-15` applied when it
    deleted `auto_discover` from this module for returning an empty config when
    it found nothing. That deletion removed the caller and left the behaviour
    one function below it.
    """
    missing = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError) as excinfo:
        GovernanceResolver.from_file(missing)
    # The message has to name the file and a way out: the failure this replaces
    # was invisible, so an exception that only says "not found" trades silence
    # for a traceback.
    assert str(missing) in str(excinfo.value)
    assert "CONNECTOR_GOVERNANCE_YAML_PATH" in str(excinfo.value)


def test_an_absent_overlay_is_still_absence(tmp_path):
    """The one caller that legitimately tolerates a missing file.

    `from_file_with_override` checks the overlay exists before loading it —
    *nothing was asked for* is a supported mode there, and it must stay one, or
    naming no overlay would become an error.
    """
    base = _write_yaml(
        tmp_path,
        """
version: 2
sources:
  datasets.a:
    access_level: internal
""",
    )
    resolver = GovernanceResolver.from_file_with_override(base, overlay_name="nope")
    assert resolver.resolve("datasets.a").access_level == "internal"


def test_from_file_v1_yaml(tmp_path):
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          access_level: internal
          classification: green
        sources:
          datasets.gold.meters:
            access_level: restricted
            classification: pii
            user_filter_column: sub
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.meters")
    assert rule.access_level == "restricted"
    assert rule.classification == "pii"
    assert rule.user_filter_column == "sub"
    # v2 fields still present with defaults
    assert rule.dataspace == DataspaceSpec()


def test_from_file_reads_the_deprecated_policy_spelling(tmp_path):
    """`policy:` still parses, and lands where the canonical block keeps it.

    The block folded into `dataspace:` in
    `the-dataspace-block-is-the-policy-block`; deployed files that still spell it
    the old way must not change meaning, which is the whole reason
    `_fold_legacy_policy` exists rather than the field just being deleted.
    """
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          access_level: internal
        sources:
          datasets.gold.grid:
            access_level: restricted
            classification: yellow
            tags: [grid]
            policy:
              obligations:
                delete_after_days: 90
            dataspace:
              expose: true
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.grid")
    assert rule.dataspace.obligations.delete_after_days == 90
    assert rule.dataspace.expose is True
    assert "grid" in rule.tags


def test_resolve_defaults_fallback(tmp_path):
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          access_level: open
        sources:
          datasets.gold.meters:
            classification: green
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.unknown")
    assert rule.access_level == "open"


def test_resolve_glob_match(tmp_path):
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          access_level: internal
        sources:
          datasets.gold.*:
            access_level: restricted
          datasets.*:
            access_level: open
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    # longer glob wins
    rule = resolver.resolve("datasets.gold.meters")
    assert rule.access_level == "restricted"


def test_resolve_exact_over_glob(tmp_path):
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          access_level: internal
        sources:
          datasets.gold.*:
            access_level: restricted
          datasets.gold.meters:
            access_level: open
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.meters")
    assert rule.access_level == "open"


def test_merge_inherits_defaults(tmp_path):
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          tags: [base_tag]
          access_level: internal
          classification: green
        sources:
          datasets.gold.meters:
            access_level: restricted
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.meters")
    # access_level overridden; classification and tags inherited
    assert rule.access_level == "restricted"
    assert rule.classification == "green"
    assert "base_tag" in rule.tags


def test_resolve_empty_config():
    resolver = GovernanceResolver(GovernanceConfig())
    rule = resolver.resolve("any.dataset")
    assert isinstance(rule, GovernanceRuleV2)
    assert rule.access_level is None


def test_row_filters_parsed(tmp_path):
    yaml_path = _write_yaml(
        tmp_path,
        """
        sources:
          datasets.silver.meters_15m:
            access_level: restricted
            classification: pii
            row_filters:
              - handler: rec_registry
                args:
                  column: sub
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.silver.meters_15m")
    assert len(rule.row_filters) == 1
    assert rule.row_filters[0].handler == "rec_registry"
    assert rule.row_filters[0].args.column == "sub"


def test_row_filters_override_defaults(tmp_path):
    """Override row_filters wins; empty override inherits from defaults."""
    yaml_path = _write_yaml(
        tmp_path,
        """
        defaults:
          row_filters:
            - handler: default_handler
              args:
                column: user_id
        sources:
          datasets.silver.meters:
            row_filters:
              - handler: rec_registry
                args:
                  column: sub
          datasets.silver.other:
            access_level: restricted
    """,
    )
    resolver = GovernanceResolver.from_file(yaml_path)
    meters = resolver.resolve("datasets.silver.meters")
    assert meters.row_filters[0].handler == "rec_registry"
    other = resolver.resolve("datasets.silver.other")
    assert other.row_filters[0].handler == "default_handler"


# ── exposed_owner_aliases ─────────────────────────────────────────────────────


def test_ownership_declared_only_in_defaults_is_found(tmp_path):
    """The shape that makes reading `config.sources` directly wrong.

    `services/connector/governance-rec/governance.yaml` declares `ownership`
    once, in `defaults:`, and never repeats it per dataset — so a collector that
    walked the raw sources would find no owner at all and report a governance
    file with owners as naming none. `resolve()` merges the defaults in, which is
    also what decides the ODRL assigner.
    """
    path = _write_yaml(
        tmp_path,
        """
        defaults:
          ownership:
            - name: example-org
              type: DATA_OWNER
          dataspace:
            expose: false
        sources:
          datasets.gold.a:
            dataspace:
              expose: true
    """,
    )

    assert exposed_owner_aliases(path) == ["example-org"]


def test_an_unexposed_dataset_does_not_onboard_its_owner(tmp_path):
    """`expose: false` publishes nothing, so its owner owns nothing here."""
    path = _write_yaml(
        tmp_path,
        """
        sources:
          datasets.gold.published:
            ownership:
              - name: publisher
            dataspace:
              expose: true
          datasets.bronze.internal:
            ownership:
              - name: internal-only
            dataspace:
              expose: false
    """,
    )

    assert exposed_owner_aliases(path) == ["publisher"]


def test_aliases_are_deduplicated_in_file_order(tmp_path):
    """Two datasets, one owner, one line — and the order is the file's."""
    path = _write_yaml(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership:
              - name: second
              - name: first
            dataspace:
              expose: true
          datasets.gold.b:
            ownership:
              - name: first
            dataspace:
              expose: true
    """,
    )

    assert exposed_owner_aliases(path) == ["second", "first"]


def test_a_dataset_overriding_the_default_owner_reports_both(tmp_path):
    """The merge is per dataset, so a default owner survives alongside an override."""
    path = _write_yaml(
        tmp_path,
        """
        defaults:
          ownership:
            - name: house-owner
          dataspace:
            expose: true
        sources:
          datasets.gold.a: {}
          datasets.gold.b:
            ownership:
              - name: other-owner
    """,
    )

    assert exposed_owner_aliases(path) == ["house-owner", "other-owner"]


def test_a_governance_file_exposing_nothing_names_no_owner(tmp_path):
    """Empty, and the caller — not this function — decides whether that is an error."""
    path = _write_yaml(
        tmp_path,
        """
        sources:
          datasets.bronze.raw:
            ownership:
              - name: somebody
    """,
    )

    assert exposed_owner_aliases(path) == []


def test_yaml_that_is_not_a_governance_file_names_the_file(tmp_path):
    """A path that does not resolve already answers in one sentence; valid YAML
    that is not governance is the same mistake and used to answer with an
    `AttributeError` from a dict comprehension. The operator who mistyped a path
    needs to be told which path."""
    path = tmp_path / "owners.yaml"
    path.write_text("- id: greenland\n- id: set-distribuzione\n")

    with pytest.raises(ValueError) as exc:
        GovernanceResolver.from_file(path)

    assert "owners.yaml" in str(exc.value)
    assert "not a governance file" in str(exc.value)


def test_a_sources_section_that_is_not_a_mapping_names_the_section(tmp_path):
    path = tmp_path / "governance.yaml"
    path.write_text("sources: [datasets.gold.grid]\n")

    with pytest.raises(ValueError) as exc:
        GovernanceResolver.from_file(path)

    assert "`sources:`" in str(exc.value)
    assert "governance.yaml" in str(exc.value)
