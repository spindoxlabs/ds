"""Read rule→requirement links off the rulebook's own text.

Many rules already name the blueprint row they answer, in the rule statement or
in its status cell: *"Every participant implements or uses a catalogue service
as part of its control plane (`DSSC-PUB-05`)"*. That is an attribution somebody
wrote deliberately, in the place a reader will see it, and keeping a second copy
of it in a manifest would create exactly the drift this repository keeps
finding — *a second copy of a vocabulary, in a module that does not own it,
drifts the moment the owner adds an indirection* (`policies.md` §6).

So it is derived instead. A derived link costs nothing to maintain, moves when
the rule text moves, and disappears when the rule does.

The manifest holds only what no file states on its own: rows deliberately
declined, rows accepted and unmet, and rows answered by a page whose specific
rule nobody has named.
"""

from __future__ import annotations

import re

from .model import Disposition, Requirement, Rule, State

#: A fully written id, as it appears in prose: `DSSC-PUB-05`, `CEEDS-STD-11`.
_FULL = re.compile(r"\b(?:DSSC|CEEDS)-[A-Z]+-\d+\b")

#: The rulebook's shorthand for a DSSC row inside a rule statement — ``(`PUB-13`)``,
#: ``(`DSO-11`)``, ``(`PTO-79`, `-80`)``. Only accepted inside parentheses,
#: because that is the form the rulebook uses for an attribution and it keeps
#: the pattern from matching ordinary prose. Backticks are optional but usual:
#: the rulebook code-spans these ids, and a pattern that required the bare form
#: matched none of the real ones.
_SHORT = re.compile(r"\(\s*`?([A-Z]{3})-(\d+)`?[^)]*\)")

#: A continuation inside the same parenthesis — ``(`PUB-19`, `-23`, `-26`)``.
#: The rulebook elides the prefix after the first id, and three of the rows a
#: rule closes are commonly written this way.
_CONTINUATION = re.compile(r"`-(\d+)`")


def derive(rules: list[Rule], requirements: list[Requirement]) -> dict[str, Disposition]:
    """Every blueprint row a rule names, mapped to the rules that name it.

    Only ids that a blueprint requirement table actually declares are returned;
    a typo in a rule cannot invent coverage. `find_orphan_ids` reports the ones
    the blueprints never declare, so a mistyped attribution is visible rather
    than silently dropped.
    """
    known = {requirement.id for requirement in requirements}
    found: dict[str, set[str]] = {}

    for rule in rules:
        text = f"{rule.statement} {rule.status_cell}"
        cited: set[str] = {match for match in _FULL.findall(text) if match in known}
        for group in _SHORT.finditer(text):
            prefix, number = group.group(1), group.group(2)
            candidate = f"DSSC-{prefix}-{number}"
            if candidate not in known:
                continue
            cited.add(candidate)
            # `(`PUB-19`, `-23`, `-26`)` — the prefix is stated once and the
            # rest of the group elides it.
            for suffix in _CONTINUATION.findall(group.group(0)):
                sibling = f"DSSC-{prefix}-{suffix}"
                if sibling in known:
                    cited.add(sibling)
        for requirement_id in cited:
            found.setdefault(requirement_id, set()).add(rule.id)

    return {
        requirement_id: Disposition(
            requirement_id=requirement_id,
            state=State.COVERED,
            rules=tuple(sorted(rule_ids)),
            note="derived from the rule text",
            derived=True,
        )
        for requirement_id, rule_ids in found.items()
    }


def merge(
    derived: dict[str, Disposition],
    manifest: dict[str, Disposition],
) -> dict[str, Disposition]:
    """Combine derived links with the manifest.

    **The manifest wins on state**, because declining or deferring a row is a
    decision and a passing mention in a rule's prose must not silently overturn
    it. Where both say `covered`, the two sets of rules are unioned: a rule that
    names the row and a manifest entry that names another rule are both true.
    """
    result: dict[str, Disposition] = dict(derived)

    for requirement_id, entry in manifest.items():
        existing = result.get(requirement_id)
        if existing is None or entry.state is not State.COVERED:
            result[requirement_id] = entry
            continue
        result[requirement_id] = Disposition(
            requirement_id=requirement_id,
            state=State.COVERED,
            rules=tuple(sorted(set(existing.rules) | set(entry.rules))),
            pages=tuple(sorted(set(existing.pages) | set(entry.pages))),
            note=entry.note or existing.note,
            derived=False,
        )

    return result
