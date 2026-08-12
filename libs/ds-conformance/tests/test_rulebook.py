from pathlib import Path

from ds_conformance.rulebook import parse_rulebook, sort_key


def page(root: Path, name: str, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")


def test_rules_are_read_with_their_page_section_and_status(tmp_path: Path) -> None:
    page(
        tmp_path,
        "policies.md",
        "## 3. What a policy says\n\n| # | Rule | Status |\n|---|---|---|\n"
        "| A-6 | `access_level: secret` is never published | **Enforced** |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert problems == []
    assert len(rules) == 1
    rule = rules[0]
    assert (rule.id, rule.page, rule.status) == ("A-6", "policies", "Enforced")
    assert rule.section == "3. What a policy says"
    assert rule.claims_enforcement


def test_a_source_table_yields_a_statusless_rule_and_no_problem(tmp_path: Path) -> None:
    # `policies.md` §4: CR-1…CR-5 state precedence and cite the blueprint row
    # each comes from. A row with no status column is not a row with an unknown
    # status, and reporting it as one would invent five defects.
    page(
        tmp_path,
        "policies.md",
        "| # | Rule | Source |\n|---|---|---|\n"
        "| **CR-1** | **Prohibition precedence.** | `DSSC-AUP-51` |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert problems == []
    assert rules[0].id == "CR-1"
    assert rules[0].status is None
    assert not rules[0].claims_enforcement


def test_a_lettered_rule_is_a_rule(tmp_path: Path) -> None:
    # `P-8a`, `D-22b`, `X-6c` are rules in their own right. A scanner assuming
    # `[A-Z]-\d+` missed nine of them for the life of the deleted projection.
    page(
        tmp_path,
        "personal-data.md",
        "| # | Rule | Status |\n|---|---|---|\n"
        "| D-11a | controller roles are declared by the producer | **Enforced** |\n"
        "| D-22b | a lettered rule | **Declared** |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert problems == []
    assert [r.id for r in rules] == ["D-11a", "D-22b"]


def test_a_rule_shaped_row_outside_a_rule_table_is_reported(tmp_path: Path) -> None:
    page(
        tmp_path,
        "policies.md",
        "| Metadatum | How | Status |\n|---|---|---|\n"
        "| A-99 | stranded in the wrong table | **Enforced** |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert rules == []
    assert [p.kind for p in problems] == ["rule-row-outside-a-rule-table"]
    assert problems[0].subject == "A-99"


def test_a_synonym_status_is_reported_against_the_rule_that_carries_it(tmp_path: Path) -> None:
    page(
        tmp_path,
        "catalogue-and-metadata.md",
        "| # | Rule | Status |\n|---|---|---|\n| C-21 | a rule | **Partially enforced** |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert [p.kind for p in problems] == ["invalid-status"]
    assert problems[0].subject == "C-21"
    # The rule is still returned — an unreadable status is a defect in the row,
    # not a reason to drop the row out of the universe and undercount.
    assert [r.id for r in rules] == ["C-21"]
    assert rules[0].status is None


def test_a_duplicate_rule_id_is_reported_rather_than_last_one_wins(tmp_path: Path) -> None:
    page(
        tmp_path,
        "a.md",
        "| # | Rule | Status |\n|---|---|---|\n| X-1 | first | **Enforced** |\n",
    )
    page(
        tmp_path,
        "b.md",
        "| # | Rule | Status |\n|---|---|---|\n| X-1 | second, different | **Declared** |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert [p.kind for p in problems] == ["duplicate-rule-id"]
    assert len(rules) == 1


def test_ids_sort_numerically_and_lettered_suffixes_follow_their_stem() -> None:
    ordered = sorted(["A-10", "A-2", "P-8b", "P-8", "P-8a", "A-1"], key=sort_key)
    assert ordered == ["A-1", "A-2", "A-10", "P-8", "P-8a", "P-8b"]


def test_the_real_rulebook_parses_completely() -> None:
    # The guard the deleted projection lacked: not "we found enough rules" but
    # "every rule-shaped row in the tree is inside a rule table and parsed".
    # A floor like `> 100` passes while nine rules are invisible, and fails when
    # work is *completed* — this asserts the property instead of a count.
    root = Path(__file__).resolve().parents[3] / "docs" / "rulebook"
    if not root.is_dir():  # pragma: no cover - only when run outside the repo
        return
    rules, problems = parse_rulebook(root)
    assert rules, "no rules parsed from the real rulebook"
    structural = [
        p
        for p in problems
        if p.kind in {"rule-row-outside-a-rule-table", "malformed-rule-row", "unparseable-rule-id"}
    ]
    assert structural == [], f"rulebook rows the parser cannot see: {structural}"
    assert len({r.id for r in rules}) == len(rules)


def test_the_generated_page_is_not_read_back_as_input(tmp_path: Path) -> None:
    # `status.md` tabulates every rule id. Parsing it would double every rule
    # and report each one as stranded outside a rule table — a generator that
    # consumes its own output measures itself.
    page(
        tmp_path,
        "policies.md",
        "| # | Rule | Status |\n|---|---|---|\n| A-1 | real | **Enforced** |\n",
    )
    page(
        tmp_path,
        "status.md",
        "| Rule | Claimed | Verdict | Layers | Evidence |\n|---|---|---|---|---|\n"
        "| `A-1` | Enforced | evidenced | unit×1 | `t` |\n",
    )
    rules, problems = parse_rulebook(tmp_path)
    assert [r.id for r in rules] == ["A-1"]
    assert problems == []
