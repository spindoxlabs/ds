"""Governance YAML loader and resolver.

Drop-in replacement for the legacy GovernanceResolver, extended to
produce GovernanceRuleV2 instances while remaining 100% backward-compatible
with v1 YAML files.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, TypeVar

import yaml

from celine.governance.merge import merge_models, merge_rules
from celine.governance.resolver import parse_rule
from pydantic import BaseModel

from .models import (
    DataspacePolicy,
    GovernanceRuleV2,
)


_M = TypeVar("_M", bound=BaseModel)


def _merged(value: _M | None) -> _M:
    """Narrow upstream's optional merge result where both operands were non-None.

    `celine.governance.merge.merge_models` is `Optional` in and `Optional` out —
    it has to be, because upstream's `dcat`, `ontology` and `dataspace` are all
    optional fields and merging *absent* with *present* is a real case. ds's one
    remaining call site cannot pass one: `GovernanceRuleV2.policy` has a
    `default_factory`, so it is always a model.

    Upstream states the same fact as `assert merged is not None  # both operands
    are non-None by signature`. This is that, named.
    """
    assert value is not None, "both merge operands were non-None"
    return value


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

        **This was a declared divergence and is no longer one.** Phase 0 measured it
        as such — upstream's `from_file` returned an empty config for an absent path
        — and phase 2 kept ds's raise regardless, on the strength of the measurement
        above. `celine-utils` 2.5 raises `FileNotFoundError` too, citing this
        repository's incident, and leaves `auto_discover` returning empty because
        discovery that finds nothing has found nothing. So the two agree and the
        method stays here only because it parses into `GovernanceRuleV2`; the message
        is ds's, since only ds knows which environment variable named the path.
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
        """Build a `GovernanceRuleV2` from one raw block.

        **The key split is upstream's, and since `celine-utils` 2.5 it is upstream's
        for a subclass too.** `parse_rule` takes the class to validate into and reads
        the known keys off *its* fields, so `policy` is claimed rather than swept into
        `extra`. Against 2.4 this function restated the split over
        `KNOWN_KEYS | {"policy"}`, because the parser named `GovernanceRule` and a
        hand-kept addition was the only way to keep ds's own block — the same
        silent-drop shape `ADR-0013` exists to end, pointed the other way. The
        restatement is gone; what is left below is the two transforms that are ds's.

        Splitting on the model rather than on a constant is also what keeps `expose`
        and `ontology` from regressing: the list this used to keep by hand omitted
        both, so a file stated them, the schema validated them, and they landed in
        `extra` reading as absent.

        Everything still goes through `model_validate` on a dict of only the keys the
        block declared — pydantic records those in `model_fields_set` and every merge
        reads it to tell *unset* from *set to a falsy value*. Constructing with
        keyword arguments, which is what ds did until phase 2, marks every field as
        set and degrades an `exclude_unset` merge to "override always wins", making
        `expose: false` inexpressible.
        """
        block: dict[str, Any] = dict(
            (data.get("governance") if "governance" in data else data) or {}
        )

        # **A malformed filter is dropped, not raised on.** Upstream keeps
        # `list[dict]` and lets pydantic refuse a non-dict entry; ds types the list,
        # so validating the raw value would turn one bad entry into a file that does
        # not load at all. Filtering here keeps the tolerance ds has always had.
        #
        # Every argument survives, not just `column` — the handler named in the
        # entry is the only thing that knows which of them it needs, and it runs in
        # the data plane. `RowFilterArgs` is `extra="allow"` for that reason.
        if "row_filters" in block:
            block["row_filters"] = [
                f
                for f in (block["row_filters"] or [])
                if isinstance(f, dict)
                and f.get("handler")
                and isinstance(f.get("args"), dict)
            ]

        # ── Canonical placement wins ────────────────────────────────────────
        # `celine-utils/schema/governance.schema.json` puts purpose, consent and
        # contract under `dataspace:`; ds historically kept them under its own
        # `policy:` block. Everything authored outside this repo — the producer
        # pipelines — uses the canonical location, so reading only `policy:` means a
        # dataset arrives with **no purpose**, its ODRL policy carries no purpose
        # constraint, and every consent check then denies for want of a stated
        # reason. Fail-closed, invisible, and wrong.
        #
        # `policy:` stays readable because deployed ds files still use it, but it is
        # the fallback now, not the source.
        policy_raw = _canonical_policy(
            block.get("dataspace") or {}, dict(block.get("policy") or {})
        )
        if policy_raw:
            block["policy"] = policy_raw
        else:
            block.pop("policy", None)

        return parse_rule(block, GovernanceRuleV2)

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
        """Overlay a whole governance file onto another — a deployer override.

        Defaults merge with defaults; a source present in both merges rule-wise; a
        source only the overlay declares is added as-is.

        `celine.governance.merge.merge_configs` is the same three rules and **still
        cannot be called**, for a reason that outlived 2.5's subclass-generic merges.
        Two, in fact. It merges each shared source with `merge_rules`, which does not
        apply ds's `policy` overlay — so every dataset an overlay touches would lose
        the union/OR on purpose, consent and contract. And it takes a
        `GovernanceConfig`, a pydantic model carrying `active` and `depends_on`,
        where ds's is a plain holder of `defaults` and `sources`; ds reads neither
        field, because both describe a *pipeline*, which is celine's side of the
        boundary rather than a dataspace connector's.

        The first reason is the load-bearing one: a subclass of upstream's config
        would fix the second and leave a merge that silently drops ds's policy rules.

        `_merge_rule` used to sit between this and `_merge` and did nothing but call
        it. Deleted with the rest of the merge layer in phase 2 of `ADR-0013`.
        """
        defaults = cls._merge(base.defaults, override.defaults)
        sources = dict(base.sources)
        for key, rule in override.sources.items():
            sources[key] = cls._merge(sources[key], rule) if key in sources else rule
        return GovernanceConfig(defaults=defaults, sources=sources)

    @staticmethod
    def _merge(base: GovernanceRuleV2, override: GovernanceRuleV2) -> GovernanceRuleV2:
        """Overlay `override` onto `base`.

        **Upstream's merge, plus the one field upstream does not model.** Until
        `celine-utils` 2.5 this function restated all nine of `merge_rules`'s rules —
        tags union, ownership and row-filters replaced when non-empty, the shallow
        `extra` merge, `ontology` whole-replaced, the nested `dcat` and `dataspace`
        merges — not because they differed but because `merge_rules` validated its
        result into `GovernanceRule` by name, and `extra="ignore"` then dropped
        `policy`, the EDC sub-objects and `sharing_offers` on the way out. 2.5 takes
        the class from the operands, so the restatement is deleted and what remains
        is exactly what is ds's.

        `policy` is that one field. It is not upstream's shape, so `merge_rules`
        overlays it generically (`exclude_unset`, dict-wise) rather than applying the
        union/OR rules `_merge_policy` states — and those rules are the difference
        between an overlay that may tighten and one that may quietly loosen.

        Top-level scalars merge on `exclude_unset` rather than ds's old `pick()` —
        *override wins unless it is `None`*. The two differ on a field an overlay
        states as `null`: `pick` inherited the base's value, this withdraws it.
        Upstream is right — it can tell *silent* from *said no* — and phase 0
        declared the change before it was made.
        """
        merged = merge_rules(base, override)
        merged.policy = _merge_policy(base.policy, override.policy)
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


# `_merge_dataspace` was here, and it is `celine.governance.merge.merge_dataspace`
# now — reached through `merge_rules`, which calls it on the rule's own operands.
# It stated the same three rules (`purpose` union, `consent_required` and
# `contract_required` OR, `expose` deliberately not OR) and existed only because
# 2.4's version validated into `DataspaceConfig` by name and threw away the EDC
# sub-objects and `sharing_offers`. 2.5 follows the operands, so `DataspaceSpec`
# goes in and `DataspaceSpec` comes out.
#
# `_merge_policy` below keeps its own copy of those rules, and the duplication is
# no longer temporary: `dataspace` and `policy` genuinely carry the same three
# facts on two models, and phase 2 decided ds's `policy` view survives — it holds
# `audience`, `obligations` and `consent`, which upstream does not model. Having
# the two agree by construction beats having them agree by review.


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
    merged = _merged(merge_models(base, override, DataspacePolicy))
    merged.purpose = sorted(set(base.purpose) | set(override.purpose))
    merged.consent.required = base.consent.required or override.consent.required
    merged.obligations.contract_required = (
        base.obligations.contract_required or override.obligations.contract_required
    )
    return merged


# `_merge_models` was here. It is `celine.governance.merge.merge_models` now, and
# upstream's docstring says where it came from: *"Ported from `ds`
# `libs/governance/resolver.py::_merge_models`, which was the only correct
# implementation of the four that existed."*
#
# So this deletion is the round trip closing, not a capability lost. Everything the
# docstring here used to explain — `exclude_unset` rather than `exclude_defaults`
# because the latter cannot tell *silent* from *said no*, and the `expose: false`
# overlay that was inexpressible until it did — is stated upstream, once, for all
# four consumers.


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
