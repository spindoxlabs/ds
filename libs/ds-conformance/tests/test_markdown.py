from pathlib import Path

from ds_conformance.markdown import normalise_header, scan_tables, split_row

HEADER = ("#", "rule", "status")


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "page.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_table_is_found_by_its_header(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "## Section one\n\n| # | Rule | Status |\n|---|---|---|\n| A-1 | first | **Enforced** |\n",
    )
    rows, malformed = scan_tables(path, {HEADER})
    assert [r.cells[0] for r in rows] == ["A-1"]
    assert rows[0].heading == "Section one"
    assert rows[0].header == HEADER
    assert malformed == []


def test_a_table_with_a_different_header_is_ignored(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "| Stage | Point | Status |\n|---|---|---|\n| Publication | sync | **Enforced** |\n",
    )
    rows, _ = scan_tables(path, {HEADER})
    assert rows == []


def test_a_header_with_no_separator_is_not_a_table(tmp_path: Path) -> None:
    path = write(tmp_path, "| # | Rule | Status |\n| A-1 | first | **Enforced** |\n")
    rows, _ = scan_tables(path, {HEADER})
    assert rows == []


def test_a_row_of_the_wrong_arity_is_reported_not_skipped(tmp_path: Path) -> None:
    # The lesson from the deleted projection: silently skipping a row that does
    # not parse is how nine rules went uncounted for the life of the tool.
    path = write(
        tmp_path,
        "| # | Rule | Status |\n|---|---|---|\n| A-1 | first | **Enforced** |\n| A-2 | broken |\n",
    )
    rows, malformed = scan_tables(path, {HEADER})
    assert [r.cells[0] for r in rows] == ["A-1"]
    assert len(malformed) == 1
    assert malformed[0].found_columns == 2
    assert malformed[0].expected_columns == 3


def test_an_escaped_pipe_does_not_split_a_cell(tmp_path: Path) -> None:
    # Rulebook prose narrates shell pipelines and ODRL alternatives; splitting
    # on an escaped pipe would turn a good row into a malformed one.
    path = write(
        tmp_path,
        "| # | Rule | Status |\n|---|---|---|\n| A-1 | a \\| b | **Enforced** |\n",
    )
    rows, malformed = scan_tables(path, {HEADER})
    assert malformed == []
    assert rows[0].cells[1] == "a | b"


def test_the_table_ends_at_the_first_non_row(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "| # | Rule | Status |\n|---|---|---|\n| A-1 | first | **Enforced** |\n"
        "\nsome prose\n\n| A-9 | not in a table | x |\n",
    )
    rows, _ = scan_tables(path, {HEADER})
    assert [r.cells[0] for r in rows] == ["A-1"]


def test_headings_track_across_tables(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "## One\n\n| # | Rule | Status |\n|---|---|---|\n| A-1 | a | **Enforced** |\n"
        "\n### Two\n\n| # | Rule | Status |\n|---|---|---|\n| A-2 | b | **Declared** |\n",
    )
    rows, _ = scan_tables(path, {HEADER})
    assert [(r.cells[0], r.heading) for r in rows] == [("A-1", "One"), ("A-2", "Two")]


def test_split_row_on_a_non_row_returns_nothing() -> None:
    assert split_row("not a row") == []


def test_normalise_header_strips_emphasis_and_case() -> None:
    assert normalise_header(["**ID**", "`Requirement`", "Force"]) == ("id", "requirement", "force")
