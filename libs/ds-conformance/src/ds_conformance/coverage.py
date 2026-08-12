"""The coverage manifest: which blueprint row is answered by which rule.

This is the one input a human writes for this tool, and it is deliberately the
*smallest* one. Everything else — the requirement universe, the rule universe,
the evidence — is read off the tree. The manifest holds only what no file can
state on its own: whether a given blueprint obligation is answered here, left
open, or deliberately declined.

`unassessed` is a first-class state and the default. A row nobody has looked at
must be distinguishable from a row somebody decided to decline, and the failure
of every previous attempt at this ledger was that the two were the same silence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import Disposition, Problem, Requirement, State

MANIFEST_VERSION = 1


def load(path: Path) -> tuple[dict[str, Disposition], list[Problem]]:
    """Read the manifest. A missing file is an empty manifest, not an error —
    the report is meaningful on day one, when everything is `unassessed`."""
    problems: list[Problem] = []
    if not path.exists():
        return {}, problems

    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}, [
            Problem(
                kind="malformed-manifest",
                subject=str(path),
                detail="top level of the coverage manifest is not a mapping",
                where=str(path),
            )
        ]

    version = raw.get("version")
    if version != MANIFEST_VERSION:
        problems.append(
            Problem(
                kind="manifest-version",
                subject=str(path),
                detail=f"version is {version!r}, this tool reads {MANIFEST_VERSION}",
                where=str(path),
            )
        )

    entries = raw.get("dispositions") or {}
    if not isinstance(entries, dict):
        return {}, problems + [
            Problem(
                kind="malformed-manifest",
                subject=str(path),
                detail="`dispositions` is not a mapping of requirement id to entry",
                where=str(path),
            )
        ]

    dispositions: dict[str, Disposition] = {}
    for requirement_id, entry in entries.items():
        if not isinstance(entry, dict):
            problems.append(
                Problem(
                    kind="malformed-disposition",
                    subject=str(requirement_id),
                    detail="entry is not a mapping",
                    where=str(path),
                )
            )
            continue

        raw_state = str(entry.get("state", "")).strip()
        try:
            state = State(raw_state)
        except ValueError:
            problems.append(
                Problem(
                    kind="invalid-disposition-state",
                    subject=str(requirement_id),
                    detail=(
                        f"state {raw_state!r} is not one of {', '.join(s.value for s in State)}"
                    ),
                    where=str(path),
                )
            )
            continue

        rules = entry.get("rules") or []
        if isinstance(rules, str):
            rules = [rules]
        pages = entry.get("pages") or []
        if isinstance(pages, str):
            pages = [pages]

        dispositions[str(requirement_id)] = Disposition(
            requirement_id=str(requirement_id),
            state=state,
            rules=tuple(str(r) for r in rules),
            pages=tuple(str(p) for p in pages),
            note=str(entry.get("note", "")).strip(),
        )

    return dispositions, problems


def validate(
    dispositions: dict[str, Disposition],
    requirements: list[Requirement],
    rule_ids: set[str],
    page_names: set[str] | None = None,
) -> list[Problem]:
    """Every structural inconsistency between the manifest and the two trees.

    None of these is a judgement about whether a disposition is *right*. They
    are all "this names something that does not exist" or "this state requires
    a field it does not have" — the class of error a tool can settle.
    """
    problems: list[Problem] = []
    known = {r.id for r in requirements}

    for requirement_id, disposition in sorted(dispositions.items()):
        if requirement_id not in known:
            problems.append(
                Problem(
                    kind="disposition-for-unknown-requirement",
                    subject=requirement_id,
                    detail="no blueprint requirement table declares this id",
                )
            )
            continue

        for rule_id in disposition.rules:
            if rule_id not in rule_ids:
                problems.append(
                    Problem(
                        kind="disposition-cites-unknown-rule",
                        subject=requirement_id,
                        detail=f"names rule {rule_id}, which no rulebook page declares",
                    )
                )

        for page in disposition.pages:
            if page_names is not None and page not in page_names:
                problems.append(
                    Problem(
                        kind="disposition-cites-unknown-page",
                        subject=requirement_id,
                        detail=f"names page {page!r}, which is not a rulebook page",
                    )
                )

        if disposition.state is State.COVERED and not (disposition.rules or disposition.pages):
            problems.append(
                Problem(
                    kind="covered-without-a-referent",
                    subject=requirement_id,
                    detail=(
                        "state is `covered` but names neither a rulebook rule nor a "
                        "rulebook page, so nothing says what answers it"
                    ),
                )
            )

        if disposition.state in (State.OPEN, State.OUT_OF_SCOPE) and not disposition.note:
            problems.append(
                Problem(
                    kind="disposition-without-a-reason",
                    subject=requirement_id,
                    detail=(
                        f"state is `{disposition.state.value}` and carries no note; "
                        "a row that is declined or deferred owes a reason"
                    ),
                )
            )

    return problems


def unassessed(
    dispositions: dict[str, Disposition],
    requirements: list[Requirement],
) -> list[Requirement]:
    """Binding rows with no disposition at all — the backlog, in blueprint order."""
    return [
        requirement
        for requirement in requirements
        if requirement.is_binding
        and dispositions.get(requirement.id, Disposition(requirement.id, State.UNASSESSED)).state
        is State.UNASSESSED
    ]
