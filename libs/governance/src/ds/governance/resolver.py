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

        policy_raw = dict(block.get("policy") or {})
        dataspace_raw = block.get("dataspace") or {}

        # ── Canonical placement wins ────────────────────────────────────────
        # `celine-utils/schema/governance.schema.json` puts these under
        # `dataspace:`; ds historically kept them under its own `policy:` block.
        # Everything authored outside this repo — demo3, celine-pipelines — uses
        # the canonical location, so reading only `policy:` means a dataset
        # arrives with **no purpose**, its ODRL policy carries no purpose
        # constraint, and every consent check then denies for want of a stated
        # reason. Fail-closed, invisible, and wrong.
        #
        # `policy:` stays readable because deployed ds files still use it, but
        # it is the fallback now, not the source.
        policy_raw = _canonical_policy(dataspace_raw, policy_raw)

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
            # v2: merged **field by field**, not wholesale.
            #
            # Replacing the whole block loses defaults the source did not
            # restate — and that is exactly the real-world layout: demo3 puts
            # `purpose` in `defaults.dataspace` and `consent_required` on the
            # dataset. Setting the second used to discard the first, leaving a
            # consent-gated dataset with no purpose, which then denies every
            # query for want of a stated reason.
            policy=_merge_policy(base.policy, override.policy),
            dataspace=_merge_models(base.dataspace, override.dataspace, DataspaceSpec),
        )
        return merged


def _canonical_policy(dataspace_raw: dict, policy_raw: dict) -> dict:
    """Merge the canonical `dataspace:` fields into ds's `policy:` shape.

    | canonical (`dataspace.*`)  | ds (`policy.*`)              |
    |----------------------------|------------------------------|
    | `purpose`                  | `purpose`                    |
    | `consent_required`         | `consent.required`           |
    | `contract_required`        | `obligations.contract_required` |

    The canonical value wins where both are present: a file that says both
    should behave the way the schema says, not the way this repo used to.
    """
    merged = dict(policy_raw)

    purpose = dataspace_raw.get("purpose")
    if purpose:
        merged["purpose"] = list(purpose)

    if "consent_required" in dataspace_raw:
        consent = dict(merged.get("consent") or {})
        consent["required"] = bool(dataspace_raw["consent_required"])
        merged["consent"] = consent

    if "contract_required" in dataspace_raw:
        obligations = dict(merged.get("obligations") or {})
        obligations["contract_required"] = bool(dataspace_raw["contract_required"])
        merged["obligations"] = obligations

    return merged


def _merge_policy(base: DataspacePolicy, override: DataspacePolicy) -> DataspacePolicy:
    """Merge the way `dataset-api` merges the same fields.

    `celine/dataset/cli/export_governance.py::_merge_dataspace` is the reference,
    because both tools read the *same files* and must reach the same conclusion —
    otherwise a dataset is consent-gated in one and open in the other, and each is
    internally consistent.

    Its rules, which are not "override wins":

    - `purpose` is a **union**, not a replacement. An overlay adds a reason for
      processing; it does not silently retract the ones the base declared.
    - `consent_required` and `contract_required` are **OR**. Once something is
      required it cannot be un-required by a file layered on top — a deployer
      override may tighten, never loosen.

    Everything else is field-wise override, as before.
    """
    merged = _merge_models(base, override, DataspacePolicy)
    merged.purpose = sorted(set(base.purpose) | set(override.purpose))
    merged.consent.required = base.consent.required or override.consent.required
    merged.obligations.contract_required = (
        base.obligations.contract_required or override.obligations.contract_required
    )
    return merged


def _merge_models(base, override, model_cls):
    """Override's explicitly-set fields on top of base, recursively.

    `exclude_defaults` is what makes "explicitly set" mean something: a field
    the source never mentioned is absent from the dump and therefore cannot
    silently overwrite an inherited value with a default.
    """

    def deep_merge(a: dict, b: dict) -> dict:
        out = dict(a)
        for key, value in b.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = deep_merge(out[key], value)
            else:
                out[key] = value
        return out

    return model_cls.model_validate(
        deep_merge(
            base.model_dump(exclude_defaults=True),
            override.model_dump(exclude_defaults=True),
        )
    )
