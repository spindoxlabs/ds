from pathlib import Path

from ds_conformance.coverage import load, unassessed, validate
from ds_conformance.model import Disposition, Force, Requirement, State


def manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "coverage.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def requirements() -> list[Requirement]:
    return [
        Requirement("DSSC-AUP-01", "a must row", Force.MUST, "§2", "a.md", 1),
        Requirement("DSSC-AUP-02", "a should row", Force.SHOULD, "§2", "a.md", 2),
        Requirement("DSSC-AUP-03", "a may row", Force.MAY, "§2", "a.md", 3),
    ]


def test_a_missing_manifest_is_an_empty_one(tmp_path: Path) -> None:
    # The report has to be meaningful on day one, when nothing is dispositioned.
    dispositions, problems = load(tmp_path / "absent.yaml")
    assert dispositions == {}
    assert problems == []


def test_entries_are_read(tmp_path: Path) -> None:
    path = manifest(
        tmp_path,
        "version: 1\ndispositions:\n"
        "  DSSC-AUP-01:\n    state: covered\n    rules: [A-3, A-4]\n"
        "  DSSC-AUP-02:\n    state: open\n    note: needs a date operand\n",
    )
    dispositions, problems = load(path)
    assert problems == []
    assert dispositions["DSSC-AUP-01"].state is State.COVERED
    assert dispositions["DSSC-AUP-01"].rules == ("A-3", "A-4")
    assert dispositions["DSSC-AUP-02"].note == "needs a date operand"


def test_a_single_rule_may_be_written_unwrapped(tmp_path: Path) -> None:
    path = manifest(
        tmp_path, "version: 1\ndispositions:\n  DSSC-AUP-01:\n    state: covered\n    rules: A-3\n"
    )
    dispositions, _ = load(path)
    assert dispositions["DSSC-AUP-01"].rules == ("A-3",)


def test_an_unknown_state_is_reported(tmp_path: Path) -> None:
    path = manifest(tmp_path, "version: 1\ndispositions:\n  DSSC-AUP-01:\n    state: probably\n")
    dispositions, problems = load(path)
    assert dispositions == {}
    assert [p.kind for p in problems] == ["invalid-disposition-state"]


def test_a_wrong_version_is_reported(tmp_path: Path) -> None:
    path = manifest(tmp_path, "version: 99\ndispositions: {}\n")
    _, problems = load(path)
    assert [p.kind for p in problems] == ["manifest-version"]


def test_a_disposition_for_an_unknown_requirement_is_reported() -> None:
    dispositions = {"DSSC-AUP-99": Disposition("DSSC-AUP-99", State.COVERED, ("A-1",))}
    problems = validate(dispositions, requirements(), {"A-1"})
    assert [p.kind for p in problems] == ["disposition-for-unknown-requirement"]


def test_a_disposition_citing_an_unknown_rule_is_reported() -> None:
    # A rule renamed in the rulebook leaves the manifest pointing at nothing,
    # and a pointer to nothing still looks like coverage.
    dispositions = {"DSSC-AUP-01": Disposition("DSSC-AUP-01", State.COVERED, ("A-404",))}
    problems = validate(dispositions, requirements(), {"A-1"})
    assert [p.kind for p in problems] == ["disposition-cites-unknown-rule"]


def test_covered_naming_neither_a_rule_nor_a_page_is_reported() -> None:
    dispositions = {"DSSC-AUP-01": Disposition("DSSC-AUP-01", State.COVERED, ())}
    problems = validate(dispositions, requirements(), {"A-1"})
    assert [p.kind for p in problems] == ["covered-without-a-referent"]


def test_a_page_is_enough_of_a_referent() -> None:
    # Weaker than a named rule and deliberately allowed: it is the granularity
    # the rulebook's own "Blueprint rows" sections have, and recording it is
    # honest where inventing a rule attribution would not be.
    dispositions = {
        "DSSC-AUP-01": Disposition("DSSC-AUP-01", State.COVERED, (), ("policies",)),
    }
    assert validate(dispositions, requirements(), {"A-1"}, {"policies"}) == []


def test_a_page_that_is_not_a_rulebook_page_is_reported() -> None:
    dispositions = {
        "DSSC-AUP-01": Disposition("DSSC-AUP-01", State.COVERED, (), ("invented",)),
    }
    problems = validate(dispositions, requirements(), {"A-1"}, {"policies"})
    assert [p.kind for p in problems] == ["disposition-cites-unknown-page"]


def test_open_and_declined_rows_owe_a_reason() -> None:
    dispositions = {
        "DSSC-AUP-01": Disposition("DSSC-AUP-01", State.OPEN, (), ""),
        "DSSC-AUP-02": Disposition("DSSC-AUP-02", State.OUT_OF_SCOPE, (), ""),
    }
    problems = validate(dispositions, requirements(), set())
    assert [p.kind for p in problems] == [
        "disposition-without-a-reason",
        "disposition-without-a-reason",
    ]


def test_only_binding_rows_appear_in_the_backlog() -> None:
    # A `may` row nobody dispositioned is not a gap; a `must` row is.
    backlog = unassessed({}, requirements())
    assert [r.id for r in backlog] == ["DSSC-AUP-01", "DSSC-AUP-02"]


def test_a_dispositioned_row_leaves_the_backlog() -> None:
    dispositions = {"DSSC-AUP-01": Disposition("DSSC-AUP-01", State.OUT_OF_SCOPE, (), "declined")}
    backlog = unassessed(dispositions, requirements())
    assert [r.id for r in backlog] == ["DSSC-AUP-02"]
