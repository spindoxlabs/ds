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

from .models import (
    DataspacePolicy,
    DataspaceSpec,
    DcatSpec,
    GovernanceOwner,
    GovernanceRuleV2,
    RowFilter,
    RowFilterArgs,
)


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
        """Load a governance file. **A path that does not resolve is an error.**

        It used to return an empty config, which is the `CI-02` shape and the
        exact reason `auto_discover` was deleted from this module (`GOV-15`,
        below) — the deletion took the caller and left the behaviour.

        What it cost, measured 2026-08-07: the connector's default
        `governance_yaml_path` is `governance/governance.yaml`, and `245ae53`
        renamed that directory to `governance-rec/`. Compose was unaffected — it
        mounts the directory at `/governance` — so only the **host-run** path
        broke, and it broke like this: the provider connector started clean,
        logged nothing, and served an empty dataset list and an empty
        `/ns/sharing-offers` while `sharing-offers.yaml` sat on disk. Every
        `task dev:*` stack since that rename has run a provider with no
        governance, and the first thing to notice was `task e2e:fast` failing on
        a fixture whose offer was right there in the file.

        *Nothing was asked for* and *what you asked for is not there* are two
        different states, and only one of them is a supported mode. This method
        is always handed a path, so it is always the second.

        Callers that legitimately tolerate absence check first and say so:
        `from_file_with_override` for the overlay, `compliance.validator` so the
        CLI reports it as a result rather than a traceback.
        """
        if not path.exists():
            raise FileNotFoundError(
                f"governance file not found: {path}. A configured path that is "
                "missing is an error, not an empty governance config — set "
                "CONNECTOR_GOVERNANCE_YAML_PATH (or the caller's equivalent) to "
                "the file you mean."
            )
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        defaults = cls._parse_rule(raw.get("defaults") or {})
        sources = {
            pattern: cls._parse_rule(rule_data or {})
            for pattern, rule_data in (raw.get("sources") or {}).items()
        }
        return cls(GovernanceConfig(defaults=defaults, sources=sources))

    # `auto_discover` was removed here (`GOV-15`). It guessed a `governance.yaml`
    # from `GOVERNANCE_CONFIG_PATH`, `PIPELINES_ROOT/apps/<app>/` or a project
    # directory, and **returned an empty config when it found nothing** — so a
    # wrong path produced a resolver that exposed no datasets and reported no
    # error, which is the `CI-02` shape. Nothing in this repository called it.
    #
    # It has callers in `celine-utils`, and they are **not these**:
    # `celine.utils.pipelines.governance.GovernanceResolver` is a parallel class
    # with its own `auto_discover`, and no sibling checkout imports
    # `ds.governance` at all. Checked before deleting, because this ledger
    # records three rows where the holder of a *"nothing uses X"* lived outside
    # this repository — the discovery conventions are celine's, and they belong
    # with the pipelines that follow them.

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
            GovernanceOwner(**o)
            if isinstance(o, dict)
            else GovernanceOwner(name=str(o))
            for o in owners_raw
        ]

        v1_keys = {
            "title",
            "description",
            "license",
            "attribution",
            "ownership",
            "access_level",
            "access_requirements",
            "classification",
            "tags",
            "retention_days",
            "documentation_url",
            "source_system",
            "user_filter_column",
            "row_filters",
        }

        policy_raw = dict(block.get("policy") or {})
        dataspace_raw = block.get("dataspace") or {}
        # The canonical DCAT-AP block. It used to fall through to `extra` — kept,
        # but untyped and read by nothing, so a producer's publisher, themes,
        # spatial and temporal coverage and `conforms_to` reached the resolver and
        # stopped there. `extra` is for keys ds does not model; this one it does.
        dcat_raw = block.get("dcat") or {}

        # ── Canonical placement wins ────────────────────────────────────────
        # `celine-utils/schema/governance.schema.json` puts these under
        # `dataspace:`; ds historically kept them under its own `policy:` block.
        # Everything authored outside this repo — the producer pipelines — uses
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
                    # Every argument, not just `column` — the handler named here
                    # is the only thing that knows which of them it needs, and it
                    # runs in the data plane. See `RowFilterArgs`.
                    args=RowFilterArgs.model_validate(f["args"]),
                )
                for f in (block.get("row_filters") or [])
                if isinstance(f, dict)
                and f.get("handler")
                and isinstance(f.get("args"), dict)
            ],
            extra={
                k: v
                for k, v in block.items()
                if k not in v1_keys | {"policy", "dataspace", "dcat"}
            },
            policy=DataspacePolicy.model_validate(policy_raw)
            if policy_raw
            else DataspacePolicy(),
            dataspace=DataspaceSpec.model_validate(dataspace_raw)
            if dataspace_raw
            else DataspaceSpec(),
            dcat=DcatSpec.model_validate(dcat_raw) if dcat_raw else DcatSpec(),
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
            access_requirements=pick(
                base.access_requirements, override.access_requirements
            ),
            classification=pick(base.classification, override.classification),
            tags=sorted(set(base.tags) | set(override.tags)),
            retention_days=pick(base.retention_days, override.retention_days),
            documentation_url=pick(base.documentation_url, override.documentation_url),
            source_system=pick(base.source_system, override.source_system),
            user_filter_column=pick(
                base.user_filter_column, override.user_filter_column
            ),
            row_filters=override.row_filters
            if override.row_filters
            else base.row_filters,
            extra={**base.extra, **override.extra},
            # v2: merged **field by field**, not wholesale.
            #
            # Replacing the whole block loses defaults the source did not
            # restate — and that is exactly the real-world layout: a producer
            # puts `purpose` in `defaults.dataspace` and `consent_required` on
            # the dataset. Setting the second used to discard the first, leaving a
            # consent-gated dataset with no purpose, which then denies every
            # query for want of a stated reason.
            policy=_merge_policy(base.policy, override.policy),
            dataspace=_merge_models(base.dataspace, override.dataspace, DataspaceSpec),
            dcat=_merge_models(base.dcat, override.dcat, DcatSpec),
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

    **`exclude_unset`, not `exclude_defaults`** (`GOV-06`). Both drop a field the
    source never mentioned — which is the point, so an unmentioned field cannot
    overwrite an inherited value with a default. They differ on a field the
    source *did* mention whose value happens to equal the default, and
    `exclude_defaults` drops that too: it cannot tell "silent" from "said no".

    That made one instruction unexpressible. `DataspaceSpec.expose` defaults to
    `False`, so an overlay saying `expose: false` — the obvious way to withdraw a
    dataset in one environment — dumped to nothing and the base's `expose: true`
    survived. The dataset stayed in the catalogue, and the overlay that withdrew
    it validated clean. The documented workaround was `access_level: secret`,
    which is a different statement about a different thing.

    Pydantic tracks this per instance in `model_fields_set`, populated by
    `model_validate` — which is how `_parse_rule` builds every one of these — and
    `model_validate` on the merged dict carries the set forward, so a chain of
    overlays keeps working.

    Generalises past `expose`: every boolean defaulting to `False` and every
    optional defaulting to `None` had the same hole, so an overlay could turn a
    flag on and never off.
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
            base.model_dump(exclude_unset=True),
            override.model_dump(exclude_unset=True),
        )
    )


def exposed_owner_aliases(path: Path) -> list[str]:
    """The owner aliases named by every dataset a governance file **exposes**.

    The set of organisations a deployment has to onboard is derivable rather than
    listed: they are the ones that own data published into the dataspace, which is
    what `ownership[].name` on an exposed dataset says. Deriving it means it cannot
    drift from the governance it was derived from — a listed set can.

    **Resolved rules, not raw sources.** `ownership` is frequently declared once in
    `defaults:` and never repeated per dataset — `services/connector/governance-rec/
    governance.yaml` is exactly that shape — so reading `config.sources` directly
    finds no owner at all. `resolve()` merges the defaults in, which is also what
    decides the ODRL assigner, so this reads the same rule the mapper does.

    **Exposed only.** `dataspace.expose: false` is the default, and an unexposed
    dataset publishes nothing into the dataspace: its owner has no data here to be
    the owner of. `compliance.checks` already treats ownership as a property of the
    exposed set for the same reason.

    Order is the file's own, deduplicated — a caller reporting one alias per line
    gets a stable list rather than a set's arbitrary order.
    """
    config = GovernanceResolver.from_file(path).config
    aliases: list[str] = []
    seen: set[str] = set()
    for dataset_name in config.sources:
        rule = GovernanceResolver(config).resolve(dataset_name)
        if not rule.dataspace.expose:
            continue
        for owner in rule.ownership:
            if owner.name and owner.name not in seen:
                seen.add(owner.name)
                aliases.append(owner.name)
    return aliases
