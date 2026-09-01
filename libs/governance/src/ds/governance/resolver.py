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

from celine.governance.merge import merge_models
from pydantic import BaseModel
from celine.governance.models import KNOWN_KEYS

from .models import (
    DataspacePolicy,
    DataspaceSpec,
    DcatSpec,
    GovernanceRuleV2,
)


_M = TypeVar("_M", bound=BaseModel)


def _merged(value: _M | None) -> _M:
    """Narrow upstream's optional merge result where both operands were non-None.

    `celine.governance.merge.merge_models` is `Optional` in and `Optional` out —
    it has to be, because upstream's `dcat`, `ontology` and `dataspace` are all
    optional fields and merging *absent* with *present* is a real case. None of
    ds's call sites can pass one: `GovernanceRuleV2` gives `policy`, `dataspace`
    and `dcat` a `default_factory`, so they are always models.

    Upstream states the same fact as `assert merged is not None  # both operands
    are non-None by signature`. This is that, once, instead of at three call sites.
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
        """Build a rule from one raw block — the same shape as upstream's `parse_rule`.

        **Goes through `model_validate` on a dict of only the keys the block
        actually declared, and that is not a style choice.** Pydantic records those
        keys in `model_fields_set`, and every merge below reads it to tell *unset*
        from *set to a falsy value*. Constructing with keyword arguments — which is
        what this did until phase 2 of `ADR-0013` — marks **every** field as set, so
        an `exclude_unset` merge degrades to "override always wins" and
        `expose: false` becomes inexpressible.

        ds got away with it only because its own merge was `pick()` on the top-level
        scalars, which reads `None` rather than the set. Adopting upstream's merge
        makes the honest field set load-bearing, so this had to change in the same
        phase.

        Not a call to `celine.governance.parse_rule` because that function validates
        into `GovernanceRule` by name, and ds needs its subclass — see `_merge`.
        The split it performs is the same, over the same `KNOWN_KEYS`.
        """
        block: dict[str, Any] = (
            data.get("governance") if "governance" in data else data
        ) or {}

        # **Upstream's key set, plus ds's one extra block.** This was a hand-kept
        # list of fourteen names, and a hand-kept list of what a *shared* grammar
        # defines is a list that goes stale silently: it omitted `expose` and
        # `ontology`, so both landed in `extra` and read as absent while the schema
        # validated them happily. That is the same failure mode upstream documents
        # beside `KNOWN_KEYS`.
        #
        # `policy` is ds's own and is **not** in upstream's set, so it has to be
        # added here or ds's own deployed files lose their policy block to `extra`
        # — the silent-drop shape this migration exists to end, pointed the other
        # way. `dataspace`, `dcat`, `expose` and `ontology` are already in it.
        known_keys = KNOWN_KEYS | {"policy"}

        payload: dict[str, Any] = {k: v for k, v in block.items() if k in known_keys}
        unknown = {k: v for k, v in block.items() if k not in known_keys}
        if unknown:
            payload["extra"] = unknown

        # **A malformed filter is dropped, not raised on.** Upstream keeps
        # `list[dict]` and lets pydantic refuse a non-dict entry; ds types the list,
        # so validating the raw value would turn one bad entry into a file that does
        # not load at all. Filtering here keeps the tolerance ds has always had.
        #
        # Every argument survives, not just `column` — the handler named in the
        # entry is the only thing that knows which of them it needs, and it runs in
        # the data plane. `RowFilterArgs` is `extra="allow"` for that reason.
        if "row_filters" in payload:
            payload["row_filters"] = [
                f
                for f in (payload["row_filters"] or [])
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
            payload.get("dataspace") or {}, dict(payload.get("policy") or {})
        )
        if policy_raw:
            payload["policy"] = policy_raw
        else:
            payload.pop("policy", None)

        return GovernanceRuleV2.model_validate(payload)

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

        `celine.governance.merge.merge_configs` is the same three rules, and is not
        called for the same reason `merge_rules` is not: it constructs upstream's
        `GovernanceConfig`, a pydantic model carrying `active` and `depends_on`,
        where ds's is a plain holder of `defaults` and `sources`. ds reads neither
        of those two fields — they describe a *pipeline*, which is celine's side of
        the boundary, not a dataspace connector's.

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

        **The generic part is upstream's** — `merge_models` is the `exclude_unset`
        deep merge, and it is the subtle half. ds had its own copy of it; upstream's
        docstring records that the copy *was* the copy upstream ported, so this is
        the fork ending rather than a new dependency.

        What is restated below are the fields whose semantics are not "override
        wins". `celine.governance.merge.merge_rules` states the same rules for the
        same reasons and is the reference for every line of it —
        **but it cannot be called.** It validates into `GovernanceRule` by name, and
        `merge_dataspace` / the `dcat` merge name `DataspaceConfig` and `DcatConfig`,
        so handing it a `GovernanceRuleV2` returns a rule with `policy`, the EDC
        sub-objects and `sharing_offers` dropped — those models are `extra="ignore"`.
        A `model_cls` parameter upstream, exactly as `merge_models` already takes
        one, would let this function be four lines. Worth asking for: upstream's own
        docstrings name ds as the consumer that subclasses these models.

        Until then the restatement is deliberate and its cost is bounded: nine lines
        that a reader can diff against upstream, rather than a second implementation
        of the merge itself.

        Top-level scalars now merge on `exclude_unset` rather than ds's old
        `pick()` — *override wins unless it is `None`*. The two differ on a field an
        overlay states as `null`: `pick` inherited the base's value, this withdraws
        it. Upstream is right — it can tell *silent* from *said no* — and phase 0
        declared the change before it was made.
        """
        merged = _merged(merge_models(base, override, GovernanceRuleV2))

        # An overlay adds keywords; it does not retract them.
        merged.tags = sorted(set(base.tags) | set(override.tags))
        # Whole replacement when non-empty — a partial owner list is not a
        # meaningful statement.
        merged.ownership = override.ownership or base.ownership
        # Whole replacement when non-empty. **Not** field-wise: filters are a set of
        # independent gates, and interleaving two lists by position would silently
        # build a filter that neither file declared.
        merged.row_filters = override.row_filters or base.row_filters
        # Dict merge, override wins per key. Shallow, deliberately — a key ds does
        # not model is a value it cannot merge meaningfully.
        merged.extra = {**base.extra, **override.extra}
        # Whole replacement. Its two fields are alternatives (`spec` XOR
        # `spec_file`), so a field-wise overlay could produce a rule declaring both
        # — which the schema forbids and a mapping resolver rejects as two answers
        # to what one column means.
        merged.ontology = (
            override.ontology if override.ontology is not None else base.ontology
        )
        merged.dcat = _merged(merge_models(base.dcat, override.dcat, DcatSpec))
        merged.dataspace = _merge_dataspace(base.dataspace, override.dataspace)
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


def _merge_dataspace(base: DataspaceSpec, override: DataspaceSpec) -> DataspaceSpec:
    """Field-wise overlay, then the three rules that are not "override wins".

    The same three as `_merge_policy`, and **that is the point**: since
    `ADR-0013` `DataspaceSpec` inherits `purpose`, `consent_required` and
    `contract_required` from upstream, so the same three facts are now on two
    models at once. ds's readers all go through `policy`, so a plain field-wise
    merge here would leave `dataspace.purpose` saying something different from
    `policy.purpose` on the same rule — an inconsistency nobody would notice
    until somebody read the field a reader does not currently use.

    - `purpose` is a **union**. An overlay adds a reason for processing; it does
      not silently retract the ones the base declared.
    - `consent_required` and `contract_required` are **OR**. Once something is
      required it cannot be un-required by a file layered on top: an overlay may
      tighten, never loosen.

    `expose` is deliberately **not** in that list. OR-ing it would mean *once
    offered, always offered* — a loosening, and the bug the `exclude_unset` merge
    was written to remove.

    Duplication with `_merge_policy` is temporary and deliberate: phase 2 decides
    whether ds's `policy` view survives at all, and until it does, having the two
    agree by construction beats having them agree by review.
    """
    merged = _merged(merge_models(base, override, DataspaceSpec))
    merged.purpose = sorted(set(base.purpose) | set(override.purpose))
    merged.consent_required = base.consent_required or override.consent_required
    merged.contract_required = base.contract_required or override.contract_required
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
