"""Governance YAML loader and resolver.

Drop-in replacement for the legacy GovernanceResolver, extended to
produce GovernanceRuleV2 instances while remaining 100% backward-compatible
with v1 YAML files.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

import yaml

from .models import GovernanceOwner, GovernanceRuleV2, DataspacePolicy, DataspaceSpec, RowFilter, RowFilterArgs


class GovernanceConfig:
    def __init__(
        self,
        defaults: GovernanceRuleV2 | None = None,
        sources: dict[str, GovernanceRuleV2] | None = None,
    ):
        self.defaults: GovernanceRuleV2 = defaults or GovernanceRuleV2()
        self.sources: dict[str, GovernanceRuleV2] = sources or {}


class GovernanceResolver:
    """Load governance.yaml and resolve a GovernanceRuleV2 for a dataset name.

    Matching precedence:
      1. Exact key match in sources
      2. Glob / fnmatch on keys (longest pattern wins)
      3. defaults
    """

    def __init__(self, config: GovernanceConfig):
        self.config = config

    @classmethod
    def from_file(cls, path: Path) -> GovernanceResolver:
        if not path.exists():
            return cls(GovernanceConfig())
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        defaults = cls._parse_rule(raw.get("defaults") or {})
        sources = {
            pattern: cls._parse_rule(rule_data or {})
            for pattern, rule_data in (raw.get("sources") or {}).items()
        }
        return cls(GovernanceConfig(defaults=defaults, sources=sources))

    @classmethod
    def auto_discover(
        cls,
        app_name: str | None = None,
        project_dir: str | None = None,
    ) -> GovernanceResolver:
        env_path = os.getenv("GOVERNANCE_CONFIG_PATH")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return cls.from_file(p)

        if app_name:
            root = Path(os.environ.get("PIPELINES_ROOT", "./"))
            candidate = root / "apps" / app_name / "governance.yaml"
            if candidate.is_file():
                return cls.from_file(candidate)

        if project_dir:
            candidate = Path(project_dir).parent / "governance.yaml"
            if candidate.is_file():
                return cls.from_file(candidate)

        return cls(GovernanceConfig())

    def resolve(self, dataset_name: str) -> GovernanceRuleV2:
        sources = self.config.sources
        if dataset_name in sources:
            return self._merge(self.config.defaults, sources[dataset_name])
        best_match: tuple[str, GovernanceRuleV2] | None = None
        for pattern, rule in sources.items():
            if fnmatch.fnmatch(dataset_name, pattern):
                if best_match is None or len(pattern) > len(best_match[0]):
                    best_match = (pattern, rule)
        if best_match:
            return self._merge(self.config.defaults, best_match[1])
        return self.config.defaults

    @staticmethod
    def _parse_rule(data: dict[str, Any]) -> GovernanceRuleV2:
        block: dict[str, Any] = (
            data.get("governance") if "governance" in data else data
        ) or {}

        owners_raw = block.get("ownership") or []
        owners = [
            GovernanceOwner(**o) if isinstance(o, dict) else GovernanceOwner(name=str(o))
            for o in owners_raw
        ]

        v1_keys = {
            "title", "description", "license", "attribution", "ownership",
            "access_level", "access_requirements", "classification", "tags",
            "retention_days", "documentation_url", "source_system",
            "user_filter_column", "row_filters",
        }

        policy_raw = block.get("policy") or {}
        dataspace_raw = block.get("dataspace") or {}

        return GovernanceRuleV2(
            title=block.get("title"),
            description=block.get("description"),
            license=block.get("license"),
            attribution=block.get("attribution"),
            ownership=owners,
            access_level=block.get("access_level"),
            access_requirements=block.get("access_requirements"),
            classification=block.get("classification"),
            tags=block.get("tags") or [],
            retention_days=block.get("retention_days"),
            documentation_url=block.get("documentation_url"),
            source_system=block.get("source_system"),
            user_filter_column=block.get("user_filter_column"),
            row_filters=[
                RowFilter(
                    handler=f["handler"],
                    args=RowFilterArgs(column=f["args"]["column"]),
                )
                for f in (block.get("row_filters") or [])
                if isinstance(f, dict) and f.get("handler") and isinstance(f.get("args"), dict)
            ],
            extra={k: v for k, v in block.items() if k not in v1_keys | {"policy", "dataspace"}},
            policy=DataspacePolicy.model_validate(policy_raw) if policy_raw else DataspacePolicy(),
            dataspace=DataspaceSpec.model_validate(dataspace_raw) if dataspace_raw else DataspaceSpec(),
        )

    @classmethod
    def from_file_with_override(
        cls,
        base_path: Path,
        overlay_name: str | None = None,
    ) -> GovernanceResolver:
        base = cls.from_file(base_path)
        name = overlay_name or os.getenv("GOVERNANCE_OVERLAY_NAME")
        if not name:
            return base
        overlay_path = base_path.parent / f"governance.{name}.yaml"
        if not overlay_path.exists():
            return base
        overlay = cls.from_file(overlay_path)
        merged = cls._merge_configs(base.config, overlay.config)
        return cls(merged)

    @classmethod
    def _merge_configs(
        cls, base: GovernanceConfig, override: GovernanceConfig
    ) -> GovernanceConfig:
        defaults = cls._merge_rule(base.defaults, override.defaults)
        sources = dict(base.sources)
        for key, rule in override.sources.items():
            if key in sources:
                sources[key] = cls._merge_rule(sources[key], rule)
            else:
                sources[key] = rule
        return GovernanceConfig(defaults=defaults, sources=sources)

    @classmethod
    def _merge_rule(
        cls, base: GovernanceRuleV2, override: GovernanceRuleV2
    ) -> GovernanceRuleV2:
        return cls._merge(base, override)

    @staticmethod
    def _merge(base: GovernanceRuleV2, override: GovernanceRuleV2) -> GovernanceRuleV2:
        def pick(a: Any, b: Any) -> Any:
            return b if b is not None else a

        # v1 merge
        merged = GovernanceRuleV2(
            title=pick(base.title, override.title),
            description=pick(base.description, override.description),
            license=pick(base.license, override.license),
            attribution=pick(base.attribution, override.attribution),
            ownership=override.ownership or base.ownership,
            access_level=pick(base.access_level, override.access_level),
            access_requirements=pick(base.access_requirements, override.access_requirements),
            classification=pick(base.classification, override.classification),
            tags=sorted(set(base.tags) | set(override.tags)),
            retention_days=pick(base.retention_days, override.retention_days),
            documentation_url=pick(base.documentation_url, override.documentation_url),
            source_system=pick(base.source_system, override.source_system),
            user_filter_column=pick(base.user_filter_column, override.user_filter_column),
            row_filters=override.row_filters if override.row_filters else base.row_filters,
            extra={**base.extra, **override.extra},
            # v2: override wins if explicitly set; otherwise base
            policy=override.policy if override.policy != DataspacePolicy() else base.policy,
            dataspace=override.dataspace if override.dataspace != DataspaceSpec() else base.dataspace,
        )
        return merged
