"""Every rule a check cites exists — `C-13`, `DSSC-DSO-12`.

`C-13` is *metadata is checked for compliance with **this rulebook***. The
projection (`docs/rulebook/rules.json`) made the rulebook machine-readable;
what was missing was any link from a finding back to the rule it enforces, so
each check carried its own private copy of the rule in a docstring, at best.

These tests exist because a citation is worse than no citation when it is wrong:
a finding naming `D-11` when the rule is `D-11a` is confidently misleading, and
nothing else in the repository would notice. So the mapping is checked **against
the projection**, which is generated from the rulebook pages — not against a
second list.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ds.governance.compliance.checks import CHECKS, Finding
from ds.governance.compliance.consent_checks import CONSENT_CHECKS
from ds.governance.compliance.rulebook import CHECK_RULES, cite, rules_for

#: `parents[4]`, and the first version said `[3]` — which resolved to
#: `libs/docs/rulebook/rules.json`, so the fixture skipped and **the one test that
#: matters here never ran**. Green, silent, and proving nothing: the failure mode
#: this whole file is about. Hence the assertion below rather than a bare skip.
PROJECTION = Path(__file__).resolve().parents[4] / "docs" / "rulebook" / "rules.json"


@pytest.fixture(scope="module")
def rulebook_ids() -> set[str]:
    assert PROJECTION.is_file(), (
        f"{PROJECTION} is missing — run `task rulebook:generate`. This is an "
        "assertion and not a skip on purpose: a skipped citation check is "
        "indistinguishable from a passing one, and the first version of this file "
        "skipped for a week's worth of a wrong path depth."
    )
    return {r["id"] for r in json.loads(PROJECTION.read_text(encoding="utf-8"))["rules"]}


def test_every_cited_rule_exists_in_the_rulebook(rulebook_ids: set[str]):
    """The whole point. A check citing a rule that is not in the rulebook is a
    claim about a decision nobody took."""
    cited = {rule for rules in CHECK_RULES.values() for rule in rules}
    missing = sorted(cited - rulebook_ids)
    assert not missing, (
        f"checks cite rules that do not exist in docs/rulebook: {missing}. Either "
        "the rule id is wrong, or the rulebook page lost a row that a check still "
        "believes in."
    )


def test_every_mapped_check_is_a_real_check():
    """A mapping for a check that no longer runs is a citation nothing emits."""
    known = set(CHECKS) | set(CONSENT_CHECKS)
    unknown = sorted(set(CHECK_RULES) - known)
    assert not unknown, (
        f"the rule map names checks that do not exist: {unknown}. A renamed or "
        "deleted check leaves its citation behind, and the finding then carries "
        "none while the map still looks complete."
    )


def test_a_finding_carries_its_rules():
    finding = Finding("offer-controller", "…")
    assert finding.rules == ("D-11", "D-11a")
    assert finding.asdict()["rules"] == ["D-11", "D-11a"]


def test_a_check_with_no_rule_is_allowed_and_publishes_none():
    """Several checks enforce a *model* invariant rather than a rulebook decision.

    Mapping them for symmetry would be inventing a citation — the exact failure
    this mapping exists to remove — so an unmapped check must degrade cleanly
    rather than be forced to name something.
    """
    finding = Finding("governance-file", "…")
    assert finding.rules == ()
    assert "rules" not in finding.asdict()


def test_the_check_name_stays_first_and_unchanged():
    """Every existing test and every operator greps on the check name.

    The citation is an addition; renaming the check to carry it would have been a
    breaking change to the one string this output has always been read by.
    """
    assert cite("dcat-ap") == "dcat-ap (C-12, C-14)"
    assert cite("governance-file") == "governance-file"


@pytest.mark.parametrize("check", sorted(set(CHECKS) | set(CONSENT_CHECKS)))
def test_rules_for_never_raises_on_any_registered_check(check: str):
    """Called on every finding, so it has to be total over the check vocabulary."""
    assert isinstance(rules_for(check), tuple)
