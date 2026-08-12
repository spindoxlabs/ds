"""The four things this tool knows about, and nothing else.

A `Requirement` comes from `docs/blueprints/`. A `Rule` comes from
`docs/rulebook/`. An `Evidence` comes from a test source file. A `Disposition`
comes from the hand-maintained coverage manifest, and it is the only one of the
four a human writes directly for this tool's benefit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# The four enforcement markers the rulebook's own honesty rule allows, and no
# synonyms — `docs/rulebook/index.md` §"Honesty rule". "Partially enforced"
# reading against six "Partly enforced" is not a finer distinction, it is a
# value nobody can grep for, which is why this is a closed set.
ENFORCED = "Enforced"
PARTLY_ENFORCED = "Partly enforced"
DECLARED = "Declared"
NOT_ENFORCED = "Not enforced"

ALLOWED_STATUSES: tuple[str, ...] = (ENFORCED, PARTLY_ENFORCED, DECLARED, NOT_ENFORCED)

# Ordered longest-first so that scanning a status cell for a marker matches
# "Partly enforced" before it can match the "enforced" inside it.
_STATUS_MATCH_ORDER: tuple[str, ...] = tuple(sorted(ALLOWED_STATUSES, key=len, reverse=True))


class Force(StrEnum):
    """The normative force of a blueprint row, as the blueprint states it.

    Five values, and `informative` is one of them rather than a parse failure:
    a third of the rows describe what a data space *is* rather than obliging
    anybody to do anything. Bucketing those as "other" made 525 rows look like
    the scanner had given up on them.
    """

    MUST = "must"
    SHOULD = "should"
    RECOMMENDED = "recommended"
    MAY = "may"
    INFORMATIVE = "informative"
    #: Genuinely unrecognised — a force the blueprints have started writing and
    #: this enum has not learned. Distinct from `informative` on purpose.
    OTHER = "other"

    @classmethod
    def parse(cls, raw: str) -> Force:
        cleaned = raw.strip().strip("*`").lower()
        for member in (cls.MUST, cls.SHOULD, cls.RECOMMENDED, cls.MAY, cls.INFORMATIVE):
            if cleaned == member.value:
                return member
        return cls.OTHER


#: The forces that must carry a disposition in the coverage manifest. `may` and
#: `recommended` rows are parsed and counted but never demanded — a data space
#: that declines an optional row owes nobody an explanation, while one that
#: silently drops a `must` owes everybody one.
BINDING_FORCES: frozenset[Force] = frozenset({Force.MUST, Force.SHOULD})


class Layer(StrEnum):
    """Which test layer a piece of evidence came from.

    Kept distinct because the layers do not prove the same thing — see
    `docs/development/testing.md`. A rule evidenced only by a unit test is
    evidenced against a mock; one evidenced by an e2e flow is evidenced against
    the platform. The report shows the split rather than a single total, so a
    reader can tell the two apart.
    """

    UNIT = "unit"
    INTEGRATION = "integration"
    JAVA = "java"
    E2E = "e2e"
    UI = "ui"


class State(StrEnum):
    """A blueprint row's disposition in this data space."""

    #: Answered by one or more named rulebook rules.
    COVERED = "covered"
    #: Accepted as binding, not yet met. Carries a note saying what is missing.
    OPEN = "open"
    #: Deliberately not done. Carries a note, and belongs in scope-and-deviations.
    OUT_OF_SCOPE = "out-of-scope"
    #: Nobody has looked at this row yet. The honest default, and the one the
    #: report exists to drive to zero.
    UNASSESSED = "unassessed"


@dataclass(frozen=True, slots=True)
class Requirement:
    """One row of a blueprint requirement table."""

    id: str
    text: str
    force: Force
    source: str
    page: str
    line: int

    @property
    def is_binding(self) -> bool:
        return self.force in BINDING_FORCES


@dataclass(frozen=True, slots=True)
class Rule:
    """One row of a rulebook rule table.

    `status` is `None` for the conflict-resolution table in `policies.md` §4,
    whose third column is `Source` rather than `Status`: `CR-1`…`CR-5` state
    precedence, and their enforcement is asserted by `A-10`…`A-12` instead. A
    row with no status column is not a row with an unknown status.
    """

    id: str
    page: str
    section: str
    statement: str
    status: str | None
    status_cell: str
    line: int

    @property
    def claims_enforcement(self) -> bool:
        """True when the row asserts the code refuses a violating case.

        These are the rows that owe evidence. `Declared` owes none by
        definition — the honesty rule defines it as a decision nothing could
        check — and `Not enforced` owes none because it claims nothing.
        """
        return self.status in (ENFORCED, PARTLY_ENFORCED)


@dataclass(frozen=True, slots=True)
class Evidence:
    """A test node that names a rule id."""

    rule_id: str
    layer: Layer
    unit: str
    node: str
    file: str
    line: int


@dataclass(frozen=True, slots=True)
class Disposition:
    """A blueprint row's entry in the coverage manifest.

    `covered` may be answered at two granularities, and the difference is
    recorded rather than smoothed over:

    - **`rules`** — a named rule answers this row. Strong: the row inherits that
      rule's verdict, so an unevidenced rule makes the row visibly unanswered.
    - **`pages`** — a rulebook page answers it, and nobody has said which rule.
      This is the granularity the rulebook's own "Blueprint rows" sections
      have. Weak: it asserts the topic is addressed, and carries no evidence,
      so it can never read as done.

    A row recorded at page level is not a defect; it is an honest statement of
    how precisely the link is known. Sharpening one to a rule is the work the
    report lists.
    """

    requirement_id: str
    state: State
    rules: tuple[str, ...] = ()
    pages: tuple[str, ...] = ()
    note: str = ""
    #: True when the link was read off a rule's own text rather than the
    #: manifest. Derived links cost nothing to maintain and cannot go stale.
    derived: bool = False


@dataclass(slots=True)
class Problem:
    """Something the tool can state as wrong without a judgement call.

    Every problem is a *structural* inconsistency — a claim with no referent, a
    referent that does not exist, a value outside a closed set. None of them is
    an opinion about whether a rule is a good rule.
    """

    kind: str
    subject: str
    detail: str
    where: str = ""


def parse_status(cell: str) -> tuple[str | None, str | None]:
    """Extract the enforcement marker from a status cell.

    Returns `(status, error)`. The marker must appear **bolded** and must be one
    of the four; nuance after a comma is for the reader and is ignored here.
    Returns an error when the cell carries a bolded phrase that looks like a
    status and is not one of the four — that is how "Partially enforced" is
    caught rather than silently bucketed.
    """
    import re

    bolded = re.findall(r"\*\*(.+?)\*\*", cell)
    for phrase in bolded:
        stripped = phrase.strip().rstrip(".,;:")
        for status in _STATUS_MATCH_ORDER:
            if stripped.lower().startswith(status.lower()):
                return status, None
    # Nothing bolded matched. If something bolded *looks* like a status claim,
    # say so rather than reporting the row as statusless.
    for phrase in bolded:
        if "enforc" in phrase.lower() or "declar" in phrase.lower():
            return None, f"unrecognised status marker {phrase.strip()!r}"
    if not bolded:
        return None, "no bolded status marker"
    return None, None


@dataclass(slots=True)
class Assessment:
    """Everything the tool measured, in one object, so the renderer is pure."""

    requirements: list[Requirement] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    dispositions: dict[str, Disposition] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)

    def evidence_for(self, rule_id: str) -> list[Evidence]:
        return [e for e in self.evidence if e.rule_id == rule_id]

    def rules_by_id(self) -> dict[str, Rule]:
        return {r.id: r for r in self.rules}
