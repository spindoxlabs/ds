"""Tests for consent-time membership check helpers."""
from __future__ import annotations

import textwrap

import pytest

from connector.services.membership_check import resolve_dataset_owner


class TestResolveDatasetOwner:
    def test_returns_owner_alias_when_ownership_present(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(textwrap.dedent("""
            defaults:
              ownership:
                - name: example-org
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """))
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test")
        assert alias == "example-org"

    def test_returns_none_when_no_ownership(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(textwrap.dedent("""
            defaults:
              access_level: open
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """))
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test")
        assert alias is None

    def test_per_dataset_ownership_overrides_defaults(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(textwrap.dedent("""
            defaults:
              ownership:
                - name: default-org
            sources:
              datasets.gold.test:
                ownership:
                  - name: specific-org
                dataspace:
                  expose: true
        """))
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test")
        assert alias == "specific-org"

    def test_overlay_ownership(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(textwrap.dedent("""
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """))
        (tmp_path / "governance.prod.yaml").write_text(textwrap.dedent("""
            defaults:
              ownership:
                - name: prod-org
        """))
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test", overlay_name="prod")
        assert alias == "prod-org"

    def test_no_ownership_with_overlay(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(textwrap.dedent("""
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """))
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test", overlay_name="missing")
        assert alias is None
