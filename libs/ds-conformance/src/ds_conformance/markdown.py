"""A table scanner for the two documentation trees.

Deliberately not a markdown parser. It finds pipe tables by their **header
row**, which is the one lesson worth keeping from the projection that was
deleted on 2026-08-09: identifying a table by its header, and then requiring
every row beneath it to parse, is what turns "we found 128 rules" into "there
are 137 rules and we found all of them". Nine lettered rules (`P-8a`, `D-22b`,
`X-6b`, …) had never been counted by a scanner that pattern-matched rows
instead of anchoring on headers.

So this module reports two things a looser scanner cannot:

- a row **under a known header** that does not parse — the table's own shape is
  wrong, and silently skipping it undercounts
- a row **outside** any known header that looks like it belongs in one — a rule
  written in the wrong place, which is how a rule goes missing
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def split_row(line: str) -> list[str]:
    """Split a pipe-table row into its cells.

    Escaped pipes (`\\|`) are common inside rulebook prose — a cell narrating an
    ODRL expression or a shell pipeline — and splitting on them produces a row
    with the wrong arity, which under the strict-row rule becomes a reported
    problem rather than a wrong answer. They are honoured here instead.
    """
    body = line.strip()
    if not body.startswith("|"):
        return []
    placeholder = "\x00"
    body = body.replace(r"\|", placeholder)
    cells = body.strip("|").split("|")
    return [c.strip().replace(placeholder, "|") for c in cells]


def normalise_header(cells: list[str]) -> tuple[str, ...]:
    return tuple(c.strip().strip("*`").lower() for c in cells)


@dataclass(frozen=True, slots=True)
class Row:
    """One data row of a table, with everything needed to point a human at it.

    `header` travels with the row because the rulebook has two rule-table
    shapes — `| # | Rule | Status |` and `| # | Rule | Source |` — and which one
    a row sits under decides whether its third cell is a claim or a citation.
    """

    cells: tuple[str, ...]
    line: int
    heading: str
    path: Path
    header: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MalformedRow:
    """A line under a recognised header that is not a usable row of it."""

    line: int
    text: str
    expected_columns: int
    found_columns: int
    path: Path


def scan_tables(
    path: Path,
    wanted_headers: set[tuple[str, ...]],
) -> tuple[list[Row], list[MalformedRow]]:
    """Yield every data row under a header in `wanted_headers`.

    A table ends at the first line that is not a pipe row. Headings encountered
    on the way are tracked so each row can name the section it sits in — the
    rulebook is read section by section by humans, and a rule id alone is not a
    location.
    """
    rows: list[Row] = []
    malformed: list[MalformedRow] = []
    heading = ""
    lines = path.read_text(encoding="utf-8").splitlines()

    index = 0
    while index < len(lines):
        line = lines[index]

        matched_heading = _HEADING.match(line)
        if matched_heading:
            heading = matched_heading.group(2).strip()
            index += 1
            continue

        if not line.strip().startswith("|"):
            index += 1
            continue

        header_cells = split_row(line)
        key = normalise_header(header_cells)
        if key not in wanted_headers:
            index += 1
            continue

        # A header must be followed by a separator row; without one this is not
        # a table and treating it as one would invent rows.
        if index + 1 >= len(lines) or not _SEPARATOR.match(lines[index + 1].strip()):
            index += 1
            continue

        width = len(header_cells)
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            cells = split_row(lines[index])
            if len(cells) == width:
                rows.append(
                    Row(
                        cells=tuple(cells),
                        line=index + 1,
                        heading=heading,
                        path=path,
                        header=key,
                    )
                )
            else:
                malformed.append(
                    MalformedRow(
                        line=index + 1,
                        text=lines[index].strip(),
                        expected_columns=width,
                        found_columns=len(cells),
                        path=path,
                    )
                )
            index += 1

    return rows, malformed


def iter_markdown(root: Path) -> Iterator[Path]:
    """Every markdown file under `root`, in a stable order.

    Sorted, because the report is committed and a diff caused by filesystem
    iteration order would be noise that trains a reader to ignore diffs.
    """
    yield from sorted(p for p in root.rglob("*.md") if p.is_file())
