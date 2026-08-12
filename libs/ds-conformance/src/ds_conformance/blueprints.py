"""Parse the blueprint requirement tables into the requirement universe.

`docs/blueprints/` is the requirements source for the whole platform
(`AGENTS.md`). Its requirement tables are uniform — 38 of them, every one
`| ID | Requirement | Force | Source |` — which is why this side of the
measurement needs no manifest and no judgement: the universe is whatever the
blueprints say it is.
"""

from __future__ import annotations

import re
from pathlib import Path

from .markdown import iter_markdown, scan_tables
from .model import Force, Problem, Requirement

REQUIREMENT_HEADER: tuple[str, ...] = ("id", "requirement", "force", "source")

_ID = re.compile(r"^(DSSC|CEEDS)-[A-Z]+-\d+$")
_ID_ANYWHERE = re.compile(r"\b(?:DSSC|CEEDS)-[A-Z]+-\d+\b")


def parse_blueprints(root: Path) -> tuple[list[Requirement], list[Problem]]:
    """Read every requirement row under `root`.

    Returns the requirements and any structural problem found on the way. A
    duplicate id is a problem rather than a silent last-one-wins, because the
    two rows may say different things and a coverage manifest can only answer
    one of them.
    """
    requirements: list[Requirement] = []
    problems: list[Problem] = []
    seen: dict[str, Requirement] = {}

    for path in iter_markdown(root):
        page = str(path.relative_to(root))
        rows, malformed = scan_tables(path, {REQUIREMENT_HEADER})

        for bad in malformed:
            problems.append(
                Problem(
                    kind="malformed-requirement-row",
                    subject=f"{page}:{bad.line}",
                    detail=(
                        f"row under a requirement header has {bad.found_columns} columns, "
                        f"expected {bad.expected_columns}: {bad.text[:120]}"
                    ),
                    where=f"{page}:{bad.line}",
                )
            )

        for row in rows:
            raw_id = row.cells[0].strip().strip("`*")
            if not _ID.match(raw_id):
                problems.append(
                    Problem(
                        kind="unparseable-requirement-id",
                        subject=f"{page}:{row.line}",
                        detail=f"first cell is not a requirement id: {row.cells[0]!r}",
                        where=f"{page}:{row.line}",
                    )
                )
                continue

            requirement = Requirement(
                id=raw_id,
                text=row.cells[1].strip(),
                force=Force.parse(row.cells[2]),
                source=row.cells[3].strip(),
                page=page,
                line=row.line,
            )

            if raw_id in seen:
                first = seen[raw_id]
                problems.append(
                    Problem(
                        kind="duplicate-requirement-id",
                        subject=raw_id,
                        detail=(
                            f"declared at {first.page}:{first.line} and again at {page}:{row.line}"
                        ),
                        where=f"{page}:{row.line}",
                    )
                )
                continue

            seen[raw_id] = requirement
            requirements.append(requirement)

    requirements.sort(key=lambda r: r.id)
    return requirements, problems


def find_orphan_ids(root: Path, known: set[str]) -> list[Problem]:
    """Report requirement ids that appear in prose but in no requirement table.

    An id that is discussed and never declared is either a typo or a row
    somebody meant to add. Either way the coverage manifest cannot reach it, so
    it is invisible to the assessment — which is exactly the class of gap this
    tool exists to surface.
    """
    problems: list[Problem] = []
    for path in iter_markdown(root):
        page = str(path.relative_to(root))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for found in _ID_ANYWHERE.findall(line):
                if found not in known:
                    problems.append(
                        Problem(
                            kind="undeclared-requirement-id",
                            subject=found,
                            detail="mentioned in prose but declared in no requirement table",
                            where=f"{page}:{number}",
                        )
                    )
    # One report per id is enough; a row cited fifteen times is one problem.
    unique: dict[str, Problem] = {}
    for problem in problems:
        unique.setdefault(problem.subject, problem)
    return sorted(unique.values(), key=lambda p: p.subject)
