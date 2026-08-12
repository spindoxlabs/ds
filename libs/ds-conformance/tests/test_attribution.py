from ds_conformance.attribution import derive, merge
from ds_conformance.model import Disposition, Force, Requirement, Rule, State


def requirement(rid: str, force: Force = Force.MUST) -> Requirement:
    return Requirement(rid, f"text for {rid}", force, "§2", "a.md", 1)


def rule(rid: str, statement: str, status: str = "**Enforced**") -> Rule:
    return Rule(rid, "policies", "§1", statement, "Enforced", status, 1)


def test_a_rule_naming_a_row_in_full_covers_it() -> None:
    reqs = [requirement("DSSC-PUB-05")]
    rules = [rule("C-1", "Every participant uses a catalogue service (`DSSC-PUB-05`)")]
    derived = derive(rules, reqs)
    assert derived["DSSC-PUB-05"].rules == ("C-1",)
    assert derived["DSSC-PUB-05"].state is State.COVERED
    assert derived["DSSC-PUB-05"].derived


def test_the_shorthand_form_is_understood() -> None:
    # The rulebook writes `(PUB-13)` as often as it writes the full id.
    reqs = [requirement("DSSC-PUB-13")]
    rules = [rule("C-15", "A publisher must be a registered participant (`PUB-13`)")]
    assert derive(rules, reqs)["DSSC-PUB-13"].rules == ("C-15",)


def test_an_attribution_in_the_status_cell_counts_too() -> None:
    reqs = [requirement("DSSC-TRF-05")]
    rules = [rule("P-12", "The list is published", "**Enforced** — closes `DSSC-TRF-05`")]
    assert derive(rules, reqs)["DSSC-TRF-05"].rules == ("P-12",)


def test_an_id_no_blueprint_declares_cannot_invent_coverage() -> None:
    # A typo in a rule must not create a row, or the coverage map grows entries
    # the blueprints have never heard of.
    reqs = [requirement("DSSC-PUB-05")]
    rules = [rule("C-1", "names `DSSC-PUB-999`, which does not exist")]
    assert derive(rules, reqs) == {}


def test_two_rules_naming_one_row_both_appear() -> None:
    reqs = [requirement("DSSC-TRF-05")]
    rules = [rule("P-12", "a (`DSSC-TRF-05`)"), rule("P-12a", "b (`DSSC-TRF-05`)")]
    assert derive(rules, reqs)["DSSC-TRF-05"].rules == ("P-12", "P-12a")


def test_the_manifest_wins_on_state() -> None:
    # Declining a row is a decision; a passing mention in a rule's prose must
    # not silently overturn it.
    derived = {"X": Disposition("X", State.COVERED, ("A-1",), derived=True)}
    manifest = {"X": Disposition("X", State.OUT_OF_SCOPE, (), note="declined")}
    assert merge(derived, manifest)["X"].state is State.OUT_OF_SCOPE


def test_both_saying_covered_unions_the_referents() -> None:
    derived = {"X": Disposition("X", State.COVERED, ("A-1",), derived=True)}
    manifest = {"X": Disposition("X", State.COVERED, ("A-2",), ("policies",))}
    merged = merge(derived, manifest)["X"]
    assert merged.rules == ("A-1", "A-2")
    assert merged.pages == ("policies",)
    assert not merged.derived


def test_a_manifest_row_the_rules_never_mention_survives() -> None:
    manifest = {"Y": Disposition("Y", State.OPEN, (), note="not yet")}
    assert merge({}, manifest)["Y"].state is State.OPEN


def test_an_elided_group_names_every_row_in_it() -> None:
    # `C-17` closes three rows and the rulebook writes them as
    # ``(`PUB-19`, `-23`, `-26`)`` — the prefix stated once.
    reqs = [requirement(f"DSSC-PUB-{n}") for n in ("19", "23", "26")]
    rules = [rule("C-17", "An unauthorised publish is denied (`PUB-19`, `-23`, `-26`)")]
    derived = derive(rules, reqs)
    assert sorted(derived) == ["DSSC-PUB-19", "DSSC-PUB-23", "DSSC-PUB-26"]


def test_an_elided_sibling_the_blueprints_do_not_declare_is_dropped() -> None:
    reqs = [requirement("DSSC-PUB-19")]
    rules = [rule("C-17", "denied (`PUB-19`, `-999`)")]
    assert sorted(derive(rules, reqs)) == ["DSSC-PUB-19"]
