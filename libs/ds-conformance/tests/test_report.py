from datetime import date

from ds_conformance.model import Assessment, Disposition, Evidence, Layer, Rule, State
from ds_conformance.report import Verdict, judge, render, summarise


def rule(rule_id: str, status: str | None) -> Rule:
    return Rule(rule_id, "policies", "§1", f"statement for {rule_id}", status, "", 10)


def evidence(rule_id: str, layer: Layer = Layer.UNIT) -> Evidence:
    return Evidence(rule_id, layer, "libs/governance", f"node::{rule_id}", "tests/t.py", 1)


def test_a_claim_with_a_test_is_evidenced() -> None:
    assert judge(rule("A-1", "Enforced"), [evidence("A-1")]).verdict is Verdict.EVIDENCED


def test_a_claim_with_no_test_is_unevidenced() -> None:
    # The finding this whole tool exists to produce.
    assert judge(rule("A-1", "Enforced"), []).verdict is Verdict.UNEVIDENCED


def test_a_partial_claim_owes_evidence_too() -> None:
    assert judge(rule("A-4", "Partly enforced"), []).verdict is Verdict.UNEVIDENCED
    assert judge(rule("A-4", "Partly enforced"), [evidence("A-4")]).verdict is Verdict.EVIDENCED


def test_a_declared_rule_owes_nothing() -> None:
    # `Declared` means nothing could enforce it automatically. Demanding a test
    # would push authors to downgrade honest decisions, which is the opposite
    # of what the honesty rule wants.
    assert judge(rule("A-13", "Declared"), []).verdict is Verdict.CONSISTENT


def test_a_declared_rule_with_tests_is_flagged_as_understated() -> None:
    assert judge(rule("A-13", "Declared"), [evidence("A-13")]).verdict is Verdict.UNDERSTATED


def test_not_enforced_with_no_tests_is_consistent() -> None:
    assert judge(rule("A-9", "Not enforced"), []).verdict is Verdict.CONSISTENT


def test_not_enforced_with_tests_is_a_contradiction() -> None:
    # The row says the platform does not keep the rule and the tree says it
    # does. One of the two is out of date and a reader cannot tell which.
    assert judge(rule("A-9", "Not enforced"), [evidence("A-9")]).verdict is Verdict.CONTRADICTED


def test_a_precedence_row_is_neither_evidenced_nor_owed() -> None:
    assert judge(rule("CR-1", None), []).verdict is Verdict.PRECEDENCE


def build() -> Assessment:
    from ds_conformance.model import Force, Requirement

    return Assessment(
        requirements=[
            Requirement("DSSC-AUP-01", "convert business rules", Force.MUST, "§2", "a.md", 1),
            Requirement("DSSC-AUP-90", "an optional row", Force.MAY, "§2", "a.md", 2),
            Requirement("DSSC-AUP-91", "a should row", Force.SHOULD, "§2", "a.md", 3),
        ],
        rules=[rule("A-1", "Enforced"), rule("A-9", "Not enforced"), rule("A-13", "Declared")],
        evidence=[evidence("A-1")],
        dispositions={
            "DSSC-AUP-01": Disposition("DSSC-AUP-01", State.COVERED, ("A-1",)),
        },
    )


def test_the_summary_counts_what_the_report_shows() -> None:
    counts = summarise(build())
    assert counts["requirements"] == 3
    assert counts["binding"] == 2  # the `may` row is not binding
    assert counts["claiming"] == 1
    assert counts["evidenced"] == 1
    assert counts["unevidenced"] == 0
    # DSSC-AUP-91 is binding and has no disposition at all.
    assert counts["unassessed"] == 1


def test_the_page_renders_and_names_its_commit() -> None:
    page = render(build(), generated_on=date(2026, 8, 10), commit="abc1234")
    assert "abc1234" in page
    assert "2026-08-10" in page
    assert "Do not edit" in page
    assert "`DSSC-AUP-01`" in page


def test_an_unevidenced_rule_is_named_in_the_page() -> None:
    assessment = build()
    assessment.evidence = []
    page = render(assessment, generated_on=date(2026, 8, 10), commit="abc1234")
    assert "Rules claiming enforcement with no test naming them" in page
    assert "`A-1`" in page


def test_a_covered_requirement_whose_rule_is_unevidenced_says_no() -> None:
    # The transitive question, and the one a reader actually has: a blueprint
    # row can be "covered" by a rule that nothing tests, and the coverage table
    # must not let that read as done.
    assessment = build()
    assessment.evidence = []
    page = render(assessment, generated_on=date(2026, 8, 10), commit="abc1234")
    assert "**no** — `A-1`" in page
