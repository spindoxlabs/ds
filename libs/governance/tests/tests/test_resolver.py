"""Tests for GovernanceResolver — YAML loading, resolving, merging."""
import textwrap
from pathlib import Path

import pytest

from ds.governance.resolver import GovernanceConfig, GovernanceResolver
from ds.governance.models import GovernanceRuleV2, DataspacePolicy


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
    base = _write_yaml(tmp_path, """
version: 2
sources:
  datasets.a:
    access_level: internal
""")
    resolver = GovernanceResolver.from_file_with_override(base, overlay_name="nope")
    assert resolver.resolve("datasets.a").access_level == "internal"


def test_from_file_v1_yaml(tmp_path):
    yaml_path = _write_yaml(tmp_path, """
        defaults:
          access_level: internal
          classification: green
        sources:
          datasets.gold.meters:
            access_level: restricted
            classification: pii
            user_filter_column: sub
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.meters")
    assert rule.access_level == "restricted"
    assert rule.classification == "pii"
    assert rule.user_filter_column == "sub"
    # v2 fields still present with defaults
    assert rule.policy == DataspacePolicy()


def test_from_file_v2_yaml(tmp_path):
    yaml_path = _write_yaml(tmp_path, """
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
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.grid")
    assert rule.policy.obligations.delete_after_days == 90
    assert rule.dataspace.expose is True
    assert "grid" in rule.tags


def test_resolve_defaults_fallback(tmp_path):
    yaml_path = _write_yaml(tmp_path, """
        defaults:
          access_level: open
        sources:
          datasets.gold.meters:
            classification: green
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.unknown")
    assert rule.access_level == "open"


def test_resolve_glob_match(tmp_path):
    yaml_path = _write_yaml(tmp_path, """
        defaults:
          access_level: internal
        sources:
          datasets.gold.*:
            access_level: restricted
          datasets.*:
            access_level: open
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    # longer glob wins
    rule = resolver.resolve("datasets.gold.meters")
    assert rule.access_level == "restricted"


def test_resolve_exact_over_glob(tmp_path):
    yaml_path = _write_yaml(tmp_path, """
        defaults:
          access_level: internal
        sources:
          datasets.gold.*:
            access_level: restricted
          datasets.gold.meters:
            access_level: open
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.gold.meters")
    assert rule.access_level == "open"


def test_merge_inherits_defaults(tmp_path):
    yaml_path = _write_yaml(tmp_path, """
        defaults:
          tags: [base_tag]
          access_level: internal
          classification: green
        sources:
          datasets.gold.meters:
            access_level: restricted
    """)
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
    yaml_path = _write_yaml(tmp_path, """
        sources:
          datasets.silver.meters_15m:
            access_level: restricted
            classification: pii
            row_filters:
              - handler: rec_registry
                args:
                  column: sub
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    rule = resolver.resolve("datasets.silver.meters_15m")
    assert len(rule.row_filters) == 1
    assert rule.row_filters[0].handler == "rec_registry"
    assert rule.row_filters[0].args.column == "sub"


def test_row_filters_override_defaults(tmp_path):
    """Override row_filters wins; empty override inherits from defaults."""
    yaml_path = _write_yaml(tmp_path, """
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
    """)
    resolver = GovernanceResolver.from_file(yaml_path)
    meters = resolver.resolve("datasets.silver.meters")
    assert meters.row_filters[0].handler == "rec_registry"
    other = resolver.resolve("datasets.silver.other")
    assert other.row_filters[0].handler == "default_handler"
