"""Build the assessment. One function, so every entry point measures the same way."""

from __future__ import annotations

from pathlib import Path

from . import attribution
from . import coverage as coverage_module
from .blueprints import find_orphan_ids, parse_blueprints
from .markers import collect_all
from .model import Assessment, Evidence, Problem
from .rulebook import parse_rulebook

BLUEPRINTS = Path("docs/blueprints")
RULEBOOK = Path("docs/rulebook")
MANIFEST = Path("docs/rulebook/coverage.yaml")


def assess(repo: Path) -> Assessment:
    """Read the tree and return everything measured, with every problem found.

    Order matters only for problem grouping; the result is otherwise a pure
    function of the checked-out tree.
    """
    requirements, requirement_problems = parse_blueprints(repo / BLUEPRINTS)
    rules, rule_problems = parse_rulebook(repo / RULEBOOK)
    evidence, marker_problems = collect_all(repo)
    manifest, manifest_problems = coverage_module.load(repo / MANIFEST)
    # Links a rule states in its own text are read off the rulebook rather than
    # copied into the manifest — see `attribution.py` for why.
    dispositions = attribution.merge(attribution.derive(rules, requirements), manifest)

    rule_ids = {rule.id for rule in rules}
    page_names = {rule.page for rule in rules}
    problems: list[Problem] = [
        *requirement_problems,
        *rule_problems,
        *marker_problems,
        *manifest_problems,
        *coverage_module.validate(dispositions, requirements, rule_ids, page_names),
        *find_orphan_ids(repo / BLUEPRINTS, {r.id for r in requirements}),
        *_markers_naming_unknown_rules(evidence, rule_ids),
    ]

    return Assessment(
        requirements=requirements,
        rules=rules,
        evidence=evidence,
        dispositions=dispositions,
        problems=problems,
    )


def _markers_naming_unknown_rules(evidence: list[Evidence], rule_ids: set[str]) -> list[Problem]:
    """A test claiming to cover a rule that does not exist.

    This is the failure mode a marker scheme introduces and a citation scheme
    does not, so it is checked rather than assumed: a rule renamed or deleted in
    the rulebook leaves markers pointing at nothing, and a marker pointing at
    nothing is evidence for nothing while still looking like diligence.
    """
    problems: dict[str, Problem] = {}
    for item in evidence:
        if item.rule_id in rule_ids:
            continue
        problems.setdefault(
            item.rule_id,
            Problem(
                kind="marker-names-unknown-rule",
                subject=item.rule_id,
                detail=(
                    "a test declares coverage of this rule and no rulebook page "
                    "declares it — renamed, deleted, or a typo"
                ),
                where=f"{item.file}:{item.line}",
            ),
        )
    return sorted(problems.values(), key=lambda p: p.subject)
