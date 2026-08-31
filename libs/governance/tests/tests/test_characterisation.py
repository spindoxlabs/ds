"""What `ds.governance` resolves, pinned before it is replaced.

`ADR-0013` decides that `celine.governance` becomes the reference implementation of
the `governance.yaml` shape and ds imports it instead of restating it. The whole
claim of that migration is **behaviour does not change** — and nothing in this
repository said what the behaviour *was*. A merge rule is stated in three
docstrings and asserted for a handful of hand-written cases; no test resolves a
real file end to end and says what came out.

So this module is the safety net, and it is deliberately of a different kind from
the tests beside it. They assert *rules* — purpose is a union, `expose` can be
withdrawn. This one asserts *outcomes*: every dataset key in
[the corpus](../corpus/README.md), resolved, field by field, against a committed
snapshot. It has no opinion about whether any of it is right. Its only job is to
notice a change, so that a migration that meant to be transparent cannot quietly
not be.

Three layers, and they answer different questions:

1. **The snapshot** (`test_resolution_matches_the_snapshot`) — did *ds* change?
   Regenerate with `task -d libs/governance characterise:refresh` and read the
   diff. A diff is not a failure to be silenced; it is the answer.
2. **The second implementation** (`test_celine_resolves_the_corpus_identically`) —
   do ds and `celine.governance` already agree? Measured 2026-08-31 over 34
   dataset keys across seven files: **they agree on every shared field**. That is
   an assertion, not a note, so the day one of them moves is the day this says so.
3. **The declared divergences** (`TestDeclaredDivergences`) — where they *do*
   differ, and what each difference costs. Every one below was measured, not
   predicted. Each asserts **both** sides, so the migration cannot adopt one
   without a deliberate answer for it.

Delete this module when the migration is finished and the behaviour it pins is
`celine.governance`'s own. Until then, a red test here is the point of the
exercise working.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from celine.governance import GovernanceResolver as CelineResolver
from celine.governance import (
    dataspace_expose,
    effective_expose,
    exposure_conflict,
    parse_rule,
)
from celine.governance.merge import merge_rules
from ds.governance.resolver import GovernanceResolver

REPO = Path(__file__).resolve().parents[4]
CORPUS = Path(__file__).resolve().parents[1] / "corpus"
SNAPSHOT = CORPUS / "resolved.json"

#: Set by `task -d libs/governance characterise:refresh` to rewrite the snapshot.
REFRESH = os.getenv("DS_CHARACTERISATION_REFRESH") == "1"


# ── the corpus ────────────────────────────────────────────────────────────────


def corpus_files() -> dict[str, Path]:
    """Every governance file in the corpus, by the label the snapshot keys on.

    The three in-repo files are read **where they live**, not copied: a copy of the
    file the stack actually syncs would drift from it, and then this harness would
    be pinning the copy. The demo3 files are copies because their repository is not
    checked out here — see `corpus/README.md`.
    """
    files = {
        "connector/governance-rec": REPO
        / "services/connector/governance-rec/governance.yaml",
        "connector/governance-grid-operator": REPO
        / "services/connector/governance-grid-operator/governance.yaml",
        "connector/tests-fixture": REPO
        / "services/connector/tests/fixtures/governance.yaml",
    }
    for path in sorted(CORPUS.glob("demo3/*.governance.yaml")):
        files[f"demo3/{path.name.removesuffix('.governance.yaml')}"] = path
    return files


OVERLAY_BASE = CORPUS / "overlay/governance.yaml"
OVERLAY_NAME = "deployment"


def test_the_corpus_is_all_there():
    """A glob that matches nothing makes every parametrised test below vacuous.

    Named counts rather than a bare truthiness check, because that is the failure
    this repository keeps hitting: `test_schema_conformance.py` carried a glob that
    had matched nothing since the day it was written, and its `assert FILES` passed
    on the other glob's results throughout.
    """
    files = corpus_files()
    missing = {label: p for label, p in files.items() if not p.is_file()}
    assert not missing, f"corpus files missing: {missing}"
    assert len(files) == 7, f"expected 7 corpus files, found {sorted(files)}"
    assert OVERLAY_BASE.is_file(), f"no overlay base at {OVERLAY_BASE}"
    assert (OVERLAY_BASE.parent / f"governance.{OVERLAY_NAME}.yaml").is_file()


# ── projections ───────────────────────────────────────────────────────────────


def ds_view(rule: Any) -> dict[str, Any]:
    """Every field `ds.governance` models, flattened for comparison.

    Deliberately not `model_dump()`. A dump follows the model, so a field removed
    from the model disappears from the snapshot **and from the diff** — which is
    precisely the change this harness exists to catch. Listing the fields by hand
    means deleting one is a diff in this file, in the same commit.
    """
    return {
        "title": rule.title,
        "description": rule.description,
        "license": rule.license,
        "attribution": rule.attribution,
        "ownership": [[o.name, o.type] for o in rule.ownership],
        "access_level": rule.access_level,
        "access_requirements": rule.access_requirements,
        "classification": rule.classification,
        "tags": list(rule.tags),
        "retention_days": rule.retention_days,
        "documentation_url": rule.documentation_url,
        "source_system": rule.source_system,
        "user_filter_column": rule.user_filter_column,
        "row_filters": [
            {"handler": f.handler, "args": f.args.model_dump()}
            for f in rule.row_filters
        ],
        "extra": rule.extra,
        "dcat": rule.dcat.model_dump(mode="json"),
        "dataspace": rule.dataspace.model_dump(mode="json"),
        "policy": rule.policy.model_dump(mode="json"),
    }


#: The fields both implementations model, in the spelling each one uses.
#:
#: ds restructured `purpose`, `consent_required` and `contract_required` out of
#: `dataspace:` into its own `policy:` block before the canonical placement
#: settled (`resolver._canonical_policy`). They are the same three facts, so they
#: are compared here as facts rather than as fields — otherwise the comparison
#: would report a disagreement that is only a spelling.
def shared_view(rule: Any, *, celine: bool) -> dict[str, Any]:
    if celine:
        space = rule.dataspace
        dcat = rule.dcat.model_dump(mode="json") if rule.dcat else _EMPTY_DCAT
        return {
            "title": rule.title,
            "description": rule.description,
            "license": rule.license,
            "attribution": rule.attribution,
            "ownership": [[o.name, o.type] for o in rule.ownership],
            "access_level": rule.access_level,
            "access_requirements": rule.access_requirements,
            "classification": rule.classification,
            "tags": sorted(rule.tags),
            "retention_days": rule.retention_days,
            "documentation_url": rule.documentation_url,
            "source_system": rule.source_system,
            "user_filter_column": rule.user_filter_column,
            "row_filters": [dict(f) for f in rule.row_filters],
            "extra": rule.extra,
            "dcat": dcat,
            "expose": bool(space and space.expose),
            "medallion": space.medallion if space else None,
            "purpose": sorted(space.purpose) if space else [],
            "consent_required": bool(space and space.consent_required),
            "contract_required": bool(space and space.contract_required),
        }
    return {
        "title": rule.title,
        "description": rule.description,
        "license": rule.license,
        "attribution": rule.attribution,
        "ownership": [[o.name, o.type] for o in rule.ownership],
        "access_level": rule.access_level,
        "access_requirements": rule.access_requirements,
        "classification": rule.classification,
        "tags": sorted(rule.tags),
        "retention_days": rule.retention_days,
        "documentation_url": rule.documentation_url,
        "source_system": rule.source_system,
        "user_filter_column": rule.user_filter_column,
        "row_filters": [
            {"handler": f.handler, "args": f.args.model_dump()}
            for f in rule.row_filters
        ],
        "extra": rule.extra,
        "dcat": rule.dcat.model_dump(mode="json"),
        "expose": rule.dataspace.expose,
        "medallion": rule.dataspace.medallion,
        "purpose": sorted(rule.policy.purpose),
        "consent_required": rule.policy.consent.required,
        "contract_required": rule.policy.obligations.contract_required,
    }


_EMPTY_DCAT = {
    "publisher_uri": None,
    "themes": [],
    "language_uris": [],
    "spatial_uris": [],
    "accrual_periodicity": None,
    "conforms_to": None,
    "temporal": None,
}


def resolve_all() -> dict[str, dict[str, Any]]:
    """Every corpus file's every dataset key, resolved by ds."""
    out: dict[str, dict[str, Any]] = {}
    for label, path in corpus_files().items():
        resolver = GovernanceResolver.from_file(path)
        out[label] = {
            key: ds_view(resolver.resolve(key))
            for key in sorted(resolver.config.sources)
        }
    overlaid = GovernanceResolver.from_file_with_override(OVERLAY_BASE, OVERLAY_NAME)
    out["overlay/deployment"] = {
        key: ds_view(overlaid.resolve(key)) for key in sorted(overlaid.config.sources)
    }
    return out


# ── layer 1: the snapshot ─────────────────────────────────────────────────────


def test_resolution_matches_the_snapshot():
    """Regenerating must produce no diff.

    If this fails the resolver changed. Run
    `task -d libs/governance characterise:refresh`, **read the diff**, and decide
    whether it is the change you meant. During `ADR-0013`'s migration the answer
    for every field but the declared divergences below is *no*.
    """
    rendered = json.dumps(resolve_all(), indent=2, sort_keys=True) + "\n"
    if REFRESH:
        SNAPSHOT.write_text(rendered, encoding="utf-8")
        pytest.skip(f"snapshot rewritten: {SNAPSHOT}")
    assert SNAPSHOT.is_file(), (
        f"no snapshot at {SNAPSHOT} — create it with "
        "`task -d libs/governance characterise:refresh`"
    )
    assert SNAPSHOT.read_text(encoding="utf-8") == rendered, (
        "the resolver's output moved. Regenerate with "
        "`task -d libs/governance characterise:refresh` and read the diff."
    )


def test_the_snapshot_covers_every_dataset_key():
    """A snapshot of an empty resolution would match itself forever."""
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(snapshot) == sorted(list(corpus_files()) + ["overlay/deployment"])
    assert sum(len(keys) for keys in snapshot.values()) == 37, (
        "the corpus changed size — confirm that is deliberate before refreshing"
    )


# ── layer 2: the second implementation ────────────────────────────────────────


@pytest.mark.parametrize("label", sorted(corpus_files()))
def test_celine_resolves_the_corpus_identically(label: str):
    """`celine.governance` over the same file must reach the same conclusions.

    This is the measurement `ADR-0013` rests on. The two implementations were
    maintained in parallel — ds's `_merge_policy` docstring names `dataset-api`'s
    `_merge_dataspace`, a *third* copy, as its reference — and the finding is that
    the parallel maintenance held: over 34 dataset keys, every shared field agrees.

    Every difference that does exist is below, named and asserted. A failure here
    is one nobody has named yet, which makes it the interesting kind.
    """
    path = corpus_files()[label]
    ds = GovernanceResolver.from_file(path)
    celine = CelineResolver.from_file(path)
    assert sorted(ds.config.sources) == sorted(celine.config.sources)
    for key in sorted(ds.config.sources):
        assert shared_view(ds.resolve(key), celine=False) == shared_view(
            celine.resolve(key), celine=True
        ), f"{label}:{key}"


def test_celine_applies_the_overlay_identically():
    """The overlay pair, through both implementations.

    The merge is where the two were most likely to have drifted — it is the part
    each of the four parsers wrote for itself — so the deployer overlay is checked
    the same way as the base files, not assumed to follow from them.
    """
    ds = GovernanceResolver.from_file_with_override(OVERLAY_BASE, OVERLAY_NAME)
    celine = CelineResolver.from_file_with_override(OVERLAY_BASE, OVERLAY_NAME)
    assert sorted(ds.config.sources) == sorted(celine.config.sources)
    for key in sorted(ds.config.sources):
        assert shared_view(ds.resolve(key), celine=False) == shared_view(
            celine.resolve(key), celine=True
        ), key


# ── layer 3: the divergences, each measured ───────────────────────────────────


class TestDeclaredDivergences:
    """Where the two implementations disagree, and what the disagreement costs.

    Each test asserts **both** sides. The migration has to answer every one of
    them; a test that asserted only ds would let an answer be "it changed" without
    anybody deciding that.
    """

    def test_expose_is_tri_state_upstream_and_absent_here(self, tmp_path):
        """[#20](https://github.com/spindoxlabs/ds/issues/20), reproduced.

        The canonical schema has **two** exposure gates: `expose` gates the
        catalogue and the query API, `dataspace.expose` gates the dataspace offer,
        and they are ANDed. ds models only the second, so `expose: false` lands in
        `extra` where nothing reads it — the rule resolves as exposed, the
        connector publishes the asset, a consumer negotiates and concludes a
        contract, and the transfer fails at a data plane that was never going to
        serve it.

        Upstream calls the same file a contradiction and says so by name. Phase 3
        closes #20 by adopting `expose` and calling `exposure_conflict` at sync
        time — not by writing a fourth copy of the rule.
        """
        path = tmp_path / "governance.yaml"
        path.write_text(
            "sources:\n  a:\n    expose: false\n    dataspace:\n      expose: true\n"
        )

        ds_rule = GovernanceResolver.from_file(path).resolve("a")
        assert ds_rule.dataspace.expose is True
        assert ds_rule.extra == {"expose": False}, (
            "ds carries the catalogue gate in `extra`, unread"
        )

        celine_rule = CelineResolver.from_file(path).resolve("a")
        assert celine_rule.expose is False
        assert effective_expose(celine_rule) is False
        assert dataspace_expose(celine_rule) is True
        assert exposure_conflict(celine_rule) is not None

    def test_the_ds_policy_block_is_unknown_upstream(self, tmp_path):
        """`policy:` is ds's own, and upstream's parser sweeps it into `extra`.

        The trap for Phase 1: `celine.governance.parse_rule` splits a block against
        the module-level `KNOWN_KEYS`, and `policy` is not in it. Subclassing
        `GovernanceRule` is not enough on its own — a subclass that adds the field
        and reuses that parser gets a `GovernanceRuleV2` whose `policy` is empty and
        whose `extra` holds the block, which is the *same* silent-drop shape this
        migration exists to end, pointed the other way.

        Deployed ds files still use `policy:` — `_canonical_policy` reads it as the
        fallback — so this is not hypothetical for the corpus this platform runs on.
        """
        path = tmp_path / "governance.yaml"
        path.write_text(
            "sources:\n"
            "  a:\n"
            "    policy:\n"
            "      purpose: [P1]\n"
            "      consent:\n"
            "        required: true\n"
        )

        ds_rule = GovernanceResolver.from_file(path).resolve("a")
        assert ds_rule.policy.purpose == ["P1"]
        assert ds_rule.policy.consent.required is True
        assert ds_rule.extra == {}

        celine_rule = CelineResolver.from_file(path).resolve("a")
        assert celine_rule.extra == {
            "policy": {"purpose": ["P1"], "consent": {"required": True}}
        }

    def test_canonical_placement_wins_over_the_ds_policy_block(self, tmp_path):
        """A file stating both must behave as the schema says.

        ds-only behaviour — upstream has one placement and so cannot have a
        tie-break. Phase 2 has to keep this or a deployed file that states both
        changes meaning.
        """
        path = tmp_path / "governance.yaml"
        path.write_text(
            "sources:\n"
            "  a:\n"
            "    policy:\n"
            "      purpose: [FromPolicy]\n"
            "    dataspace:\n"
            "      purpose: [FromDataspace]\n"
        )
        rule = GovernanceResolver.from_file(path).resolve("a")
        assert rule.policy.purpose == ["FromDataspace"]

    def test_odrl_action_is_dropped_here_and_carried_upstream(self, tmp_path):
        """A third dropped field, and `ADR-0013` names only two.

        `dataspace.odrl_action` is in the canonical schema and in every demo3 file
        in the corpus. `DataspaceSpec` has no such field and `dataspace` is excluded
        from `extra`, so ds does not merely fail to read it — it cannot see that it
        was said. Harmless today because nothing here would act on it; recorded
        because "ds's model is a subset" is a claim whose extent nobody had measured.
        """
        path = tmp_path / "governance.yaml"
        path.write_text("sources:\n  a:\n    dataspace:\n      odrl_action: transfer\n")

        ds_rule = GovernanceResolver.from_file(path).resolve("a")
        assert "odrl_action" not in ds_rule.dataspace.model_dump()
        assert ds_rule.extra == {}, (
            "not even in extra — `dataspace` is excluded from it"
        )

        assert (
            CelineResolver.from_file(path).resolve("a").dataspace.odrl_action
            == "transfer"
        )

    def test_ontology_does_not_actually_dict_merge(self, tmp_path):
        """The latent divergence `ADR-0013` predicts is **not reproducible**.

        The ADR says ds dict-merges `ontology` per key and so can produce a rule
        declaring both `spec` and `spec_file`, which the schema forbids. It cannot:
        `extra` merges shallowly (`{**base.extra, **override.extra}`), so the
        override's whole `ontology` dict replaces the base's — the same outcome
        upstream reaches deliberately with `merge_rules`' whole replacement.

        The real difference is smaller and worth stating accurately: ds has no typed
        field and reads it nowhere, upstream models it. Recorded here rather than
        left in the ADR as a cost, because an overstated cost is still a wrong fact.
        """
        path = tmp_path / "governance.yaml"
        path.write_text(
            "defaults:\n"
            "  ontology:\n"
            "    spec: shared_map\n"
            "sources:\n"
            "  a:\n"
            "    ontology:\n"
            "      spec_file: ./local.yaml\n"
        )

        ds_rule = GovernanceResolver.from_file(path).resolve("a")
        assert ds_rule.extra == {"ontology": {"spec_file": "./local.yaml"}}

        celine_rule = CelineResolver.from_file(path).resolve("a")
        assert celine_rule.ontology.spec is None
        assert celine_rule.ontology.spec_file == "./local.yaml"

    def test_a_missing_file_raises_here_and_returns_empty_upstream(self, tmp_path):
        """**The one divergence ds must keep, and a finding for upstream.**

        `from_file` on an absent path returns an empty config upstream. That is the
        `CI-02` shape and the exact behaviour ds deleted twice: `GOV-15` removed
        `auto_discover` for it, and the fix landed in `from_file` on 2026-08-07
        after every `task dev:*` provider since `245ae53` had run with *no
        governance* — no datasets, no sharing offers — starting clean and logging
        nothing.

        So Phase 2 cannot delegate `from_file` wholesale. *Nothing was asked for*
        and *what you asked for is not there* are different states, and only the
        first is a supported mode; ds is always handed a path, so it is always the
        second. Callers that legitimately tolerate absence check first and say so.
        """
        missing = tmp_path / "nope.yaml"

        with pytest.raises(FileNotFoundError):
            GovernanceResolver.from_file(missing)

        assert CelineResolver.from_file(missing).config.sources == {}

    def test_a_scalar_set_to_null_in_an_override(self):
        """ds cannot clear a scalar; upstream can.

        ds's merge is `pick(base, override)` — *override wins unless it is `None`* —
        so an overlay stating `license: null` inherits the base's licence instead of
        withdrawing it. Upstream merges on `exclude_unset`, which distinguishes
        *silent* from *said no*, and the null wins.

        Not reachable from the corpus: `license: null` and `documentation_url: null`
        appear in every demo3 file's `defaults`, but no overlay states one. Latent,
        and adopting upstream's merge changes it — which is a behaviour change to
        declare rather than to discover.
        """
        base = GovernanceResolver._parse_rule({"title": "T"})
        override = GovernanceResolver._parse_rule({"title": None})
        assert GovernanceResolver._merge(base, override).title == "T"

        assert (
            merge_rules(parse_rule({"title": "T"}), parse_rule({"title": None})).title
            is None
        )

    def test_malformed_row_filters_are_dropped_here_and_rejected_upstream(
        self, tmp_path
    ):
        """ds is lenient where upstream is typed.

        ds builds `RowFilter` / `RowFilterArgs` and skips anything that is not a dict
        carrying both `handler` and `args`. Upstream keeps `list[dict]`, so a filter
        missing its handler survives as a raw dict and a non-dict entry fails
        validation outright.

        Phase 1 re-types `row_filters` on the subclass, which is what keeps
        `subject_column` and the data-plane contract working. What it must not do
        silently is change which malformed files load: a filter dropped without a
        word is a dataset served unfiltered.
        """
        path = tmp_path / "governance.yaml"
        path.write_text(
            "sources:\n"
            "  a:\n"
            "    row_filters:\n"
            "      - handler: h1\n"
            "        args: {column: c}\n"
            "      - handler: h2\n"
            "      - args: {column: c2}\n"
        )

        ds_rule = GovernanceResolver.from_file(path).resolve("a")
        assert [(f.handler, f.args.column) for f in ds_rule.row_filters] == [
            ("h1", "c")
        ]

        celine_rule = CelineResolver.from_file(path).resolve("a")
        assert len(celine_rule.row_filters) == 3, (
            "kept whole, handler-less entry and all"
        )

        path.write_text("sources:\n  a:\n    row_filters: ['junk']\n")
        assert GovernanceResolver.from_file(path).resolve("a").row_filters == []
        with pytest.raises(Exception):
            CelineResolver.from_file(path).resolve("a")
