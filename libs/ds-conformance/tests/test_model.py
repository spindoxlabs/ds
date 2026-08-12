import pytest

from ds_conformance.model import ALLOWED_STATUSES, Force, Rule, parse_status


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("**Enforced**", "Enforced"),
        ("**Declared**", "Declared"),
        ("**Not enforced**", "Not enforced"),
        ("**Partly enforced**", "Partly enforced"),
        ("**Enforced** when the profile declares one", "Enforced"),
        ("**Enforced**, untested", "Enforced"),
        ("**Enforced.** `FailClosedTest` covers this", "Enforced"),
        ("**Not enforced, and deliberately not emitted** — a decision", "Not enforced"),
    ],
)
def test_the_marker_is_read_and_the_nuance_after_it_ignored(cell: str, expected: str) -> None:
    status, error = parse_status(cell)
    assert (status, error) == (expected, None)


def test_partly_enforced_is_not_read_as_enforced() -> None:
    # "Partly enforced" contains "enforced"; matching longest-first is what
    # keeps a partial claim from being counted as a full one.
    assert parse_status("**Partly enforced** — half of it")[0] == "Partly enforced"


def test_a_synonym_is_an_error_not_a_bucket() -> None:
    # `docs/rulebook/index.md`: "Partially enforced" reading against six
    # "Partly enforced" is a value nobody can grep for, so it must be caught
    # rather than quietly normalised into the nearest allowed marker.
    status, error = parse_status("**Partially enforced**")
    assert status is None
    assert error is not None
    assert "Partially enforced" in error


def test_a_cell_with_no_bold_reports_why() -> None:
    status, error = parse_status("Enforced")
    assert status is None
    assert error == "no bolded status marker"


def test_a_cell_that_is_not_a_status_claim_at_all_reports_the_absence() -> None:
    # A `| # | Rule | Source |` cell cites a blueprint row and claims nothing.
    # It reads as "no marker" here; what keeps that from being reported as a
    # defect is that `rulebook.py` calls this only under a `Status` header.
    # `test_rulebook.py` pins that boundary.
    assert parse_status("`DSSC-AUP-51`") == (None, "no bolded status marker")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("must", Force.MUST),
        ("should", Force.SHOULD),
        ("**must**", Force.MUST),
        (" Should ", Force.SHOULD),
        ("recommended", Force.RECOMMENDED),
        ("may", Force.MAY),
        ("must (conditional)", Force.OTHER),
    ],
)
def test_force_parsing(raw: str, expected: Force) -> None:
    assert Force.parse(raw) is expected


def test_only_enforcement_claims_owe_evidence() -> None:
    def rule(status: str | None) -> Rule:
        return Rule("X-1", "page", "s", "statement", status, "", 1)

    assert rule("Enforced").claims_enforcement
    assert rule("Partly enforced").claims_enforcement
    # A decision nothing could check owes no test, and a row that claims
    # nothing owes nothing either.
    assert not rule("Declared").claims_enforcement
    assert not rule("Not enforced").claims_enforcement
    assert not rule(None).claims_enforcement


def test_the_allowed_statuses_are_the_four_the_honesty_rule_names() -> None:
    assert set(ALLOWED_STATUSES) == {"Enforced", "Partly enforced", "Declared", "Not enforced"}
