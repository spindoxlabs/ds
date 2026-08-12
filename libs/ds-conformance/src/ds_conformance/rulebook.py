"""Parse the rulebook's rule tables.

Every rule table is `| # | Rule | Status |`, with one exception: the
conflict-resolution table in `policies.md` §4 is `| # | Rule | Source |`, and
that is not an oversight. `CR-1`…`CR-5` state precedence and cite the blueprint
row each comes from; whether they *hold* is asserted by `A-10`, `A-11` and
`A-12`, which are ordinary rules with ordinary statuses. A row with no status
column is not a row with an unknown status, so this module keeps the two
apart.

**This module reads claims. It does not believe them.** The status column is
recorded as `claimed`, and what makes the assessment a measurement is
`markers.py` on the other side of it.
"""

from __future__ import annotations

import re
from pathlib import Path

from .markdown import iter_markdown, scan_tables, split_row
from .model import ALLOWED_STATUSES, Problem, Rule, parse_status

STATUS_HEADER: tuple[str, ...] = ("#", "rule", "status")
SOURCE_HEADER: tuple[str, ...] = ("#", "rule", "source")

#: A rule id: one or two letters, a number, an optional lettered suffix.
#: The suffix is load-bearing — `P-8a`, `D-22b`, `X-6c` are rules in their own
#: right, and a scanner that assumed `[A-Z]-\d+` missed nine of them.
RULE_ID = re.compile(r"^([A-Z]{1,2})-(\d+)([a-z]?)$")

_RULE_ROW_SHAPE = re.compile(r"^\|\s*\*{0,2}`?[A-Z]{1,2}-\d+[a-z]?`?\*{0,2}\s*\|")

#: Pages under `docs/rulebook/` that this tool writes. They must not be read
#: back as input: `status.md` tabulates every rule id, so parsing it would
#: double every rule and report each one as stranded outside a rule table. A
#: generator that consumes its own output measures itself.
GENERATED_PAGES: frozenset[str] = frozenset({"status"})


def _clean_id(cell: str) -> str:
    return cell.strip().strip("*").strip("`").strip("*").strip()


def sort_key(rule_id: str) -> tuple[str, int, str]:
    """Sort `A-2` before `A-10`, and `P-8` before `P-8a`."""
    matched = RULE_ID.match(rule_id)
    if not matched:
        return (rule_id, 0, "")
    return (matched.group(1), int(matched.group(2)), matched.group(3))


def parse_rulebook(root: Path) -> tuple[list[Rule], list[Problem]]:
    """Read every rule row under `root`, and report every rule-shaped row that
    is not in a rule table."""
    rules: list[Rule] = []
    problems: list[Problem] = []
    seen: dict[str, Rule] = {}

    for path in iter_markdown(root):
        page = path.stem
        if page in GENERATED_PAGES:
            continue
        rows, malformed = scan_tables(path, {STATUS_HEADER, SOURCE_HEADER})
        in_table_lines = {row.line for row in rows} | {bad.line for bad in malformed}

        for bad in malformed:
            problems.append(
                Problem(
                    kind="malformed-rule-row",
                    subject=f"{page}:{bad.line}",
                    detail=(
                        f"row under a rule header has {bad.found_columns} columns, "
                        f"expected {bad.expected_columns}: {bad.text[:120]}"
                    ),
                    where=f"{page}:{bad.line}",
                )
            )

        for row in rows:
            rule_id = _clean_id(row.cells[0])
            if not RULE_ID.match(rule_id):
                problems.append(
                    Problem(
                        kind="unparseable-rule-id",
                        subject=f"{page}:{row.line}",
                        detail=f"first cell of a rule table is not a rule id: {row.cells[0]!r}",
                        where=f"{page}:{row.line}",
                    )
                )
                continue

            header_is_status = row.header == STATUS_HEADER
            status_cell = row.cells[2].strip()
            status: str | None = None

            if header_is_status:
                status, error = parse_status(status_cell)
                if error:
                    problems.append(
                        Problem(
                            kind="invalid-status",
                            subject=rule_id,
                            detail=(
                                f"{error}; the honesty rule allows only "
                                f"{', '.join(ALLOWED_STATUSES)}"
                            ),
                            where=f"{page}:{row.line}",
                        )
                    )

            rule = Rule(
                id=rule_id,
                page=page,
                section=row.heading,
                statement=row.cells[1].strip(),
                status=status,
                status_cell=status_cell,
                line=row.line,
            )

            if rule_id in seen:
                first = seen[rule_id]
                problems.append(
                    Problem(
                        kind="duplicate-rule-id",
                        subject=rule_id,
                        detail=(
                            f"declared at {first.page}:{first.line} and again at {page}:{row.line}"
                        ),
                        where=f"{page}:{row.line}",
                    )
                )
                continue

            seen[rule_id] = rule
            rules.append(rule)

        # A rule-shaped row outside every rule table. This is the check that
        # would have caught the nine lettered rules earlier: they existed, they
        # were readable, and no count included them.
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if number in in_table_lines:
                continue
            if _RULE_ROW_SHAPE.match(line.strip()):
                candidate = _clean_id(split_row(line)[0])
                problems.append(
                    Problem(
                        kind="rule-row-outside-a-rule-table",
                        subject=candidate,
                        detail=(
                            "a row starting with a rule id sits outside any "
                            "'| # | Rule | Status |' table, so no count includes it"
                        ),
                        where=f"{page}:{number}",
                    )
                )

    rules.sort(key=lambda r: sort_key(r.id))
    return rules, problems
