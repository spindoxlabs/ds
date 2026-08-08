"""The rulebook, read as data rather than as prose.

`docs/rulebook/` is this dataspace's compliance record: 137 numbered rules, each
with a status and, where one exists, the evidence that backs it. `DSSC-DSO-12`
(rule `C-13`) asks that metadata be checked against that rulebook, and it could
not be, for a reason that had nothing to do with metadata: **nothing read the
document**. It is nine markdown pages, and every claim in it was maintained by
hand.

**Why this matters more than it sounds.** On 2026-08-08 five of the ten rows in
`scope-and-deviations.md` §4 — the *known non-conformances* table — were already
closed, and the page still carried them. Every one understated the platform.
`policies.md` had five stale statuses for the same reason. A compliance record
that drifts silently is the artifact an assessor reads, and it had drifted in the
one direction nobody checks for: the code got better and the page did not move.

So the projection and the drift check are the same tool. This module is the
projection; `tests/test_rulebook_projection.py` is the check.

**Why it lives here.** The invariant spans every page of `docs/rulebook/` and
belongs to no unit — the same argument `test_published_links_resolve.py` and
`test_build_covers_every_stack.py` make — and `libs/ds-e2e` runs in CI. It is
also the same shape as `route_inventory.py`: derived from a source of truth
rather than kept beside it.

**The markdown stays the source.** `docs/rulebook/rules.json` is generated from
it, never the other way round. A rule is written as prose because prose is what
an assessor reads; this is a view of it.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RULEBOOK = ROOT / "docs" / "rulebook"
PROJECTION = RULEBOOK / "rules.json"

#: The closed status vocabulary. Anything else is drift, not a nuance — the
#: page that read `Partially enforced` while six others read `Partly enforced`
#: was not making a finer distinction, it was a typo nobody could grep for.
#:
#: Qualifiers after a comma are kept in `status_raw` and dropped from `status`:
#: "Enforced, untested" and "Enforced, with a declared deviation" are both
#: *enforced*, and the qualifier is prose for a reader, not a fourth state.
STATUSES = ("enforced", "partly enforced", "not enforced", "declared")

#: `| C-13 | the rule | **Status** — evidence |`
#:
#: The trailing letter is not optional decoration: nine rules are lettered
#: (`D-22a`, `P-8a`, `P-12b`, `X-6b`, …), added beside an existing rule rather
#: than at the end of a page so the numbering after them did not shift.
_ROW = re.compile(
    r"^\|\s*(?P<id>[A-Z]+-\d+[a-z]?)\s*\|\s*(?P<text>.+?)\s*\|\s*(?P<status>.+?)\s*\|\s*$"
)
_ID_ORDER = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<number>\d+)(?P<suffix>[a-z]?)$")

#: The header every rule table carries, and the thing that makes this parse
#: **total** rather than best-effort.
#:
#: The distinction is the whole reliability argument. A parser that scans for
#: lines *looking like* rules decides what is a rule by pattern, so anything the
#: pattern does not anticipate is silently not a rule — which is exactly how
#: nine lettered ids went uncounted while a guard reading `> 100` passed at 128
#: of 137. Nothing was broken enough to notice; the record simply said less than
#: it did.
#:
#: Here the *header* decides. Every row beneath one must parse or the parse
#: fails, naming page and line — and `orphan_rule_rows` closes the other
#: direction, so a whole table written with a different header cannot go
#: unnoticed either. Both ways closed, a silent drop is unrepresentable, which
#: is the property a schema would have bought and the one that was missing.
_RULE_TABLE_HEADER = re.compile(r"^\|\s*#\s*\|\s*Rule\s*\|\s*Status\s*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|\s*$")

#: A bare (un-backticked) rule id in the first cell. Blueprint rows are written
#: `` `DSSC-AUP-13` `` and so do not match — which is what keeps the "Closed
#: since this table was last accurate" table from reading as rules.
_ORPHAN_ROW = re.compile(r"^\|\s*[A-Z]+-\d+[a-z]?\s*\|")


class RulebookParseError(RuntimeError):
    """A rule table row that could not be read.

    Raised rather than skipped. A compliance record whose parser shrugs at what
    it does not understand reports fewer rules than the document states, and
    reports it as a success.
    """


_STATUS = re.compile(r"^\*\*(?P<status>[^*]+)\*\*")
_BACKTICKED = re.compile(r"`([^`]+)`")
_REPO_PATH = re.compile(r"[\w.\-]+(?:/[\w.\-]+)+")


def _is_repo_path(token: str) -> bool:
    """Does this backticked token name a file in this repository?

    Conservative on purpose. The status column is prose with code in it, so most
    backticks hold identifiers (`consent_snapshot_hash`), types (`str | None`)
    and routes (`POST /admin/disclosure`). Only a slash-separated token with no
    spaces and no leading slash is treated as a path — a route always has the
    leading slash, and an identifier never has the separator.
    """
    token = token.strip()
    if token.startswith(("/", "http://", "https://")) or " " in token:
        return False
    return _REPO_PATH.fullmatch(token.split(":")[0]) is not None and "/" in token


def resolve_evidence(token: str) -> Path | None:
    """The file *token* names, or `None`.

    Two forms are accepted because the rulebook uses both: a path from the
    repository root, and a path relative to the unit under discussion
    (`tests/test_status_list_allocation.py` inside a page about the identity
    registry). The second resolves only when exactly one file in the repository
    ends with it — an ambiguous suffix is not evidence, it is a guess.
    """
    relative = token.split(":")[0]
    direct = ROOT / relative
    if direct.exists():
        return direct

    suffix = "/" + relative
    matches = [
        p
        for p in ROOT.rglob("*" + Path(relative).name)
        if str(p).endswith(suffix)
        and not {".venv", "node_modules", "site", "__pycache__", ".git", "build"}
        & set(p.relative_to(ROOT).parts)
    ]
    return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class Rule:
    """One numbered row of one rulebook page."""

    id: str
    page: str
    prefix: str
    status: str
    status_raw: str
    text: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Deviation:
    """One row of `scope-and-deviations.md` §4 — a rule the code does not keep.

    `blueprint_rows` are the DSSC/CEEDS ids the row answers for; `rules` are the
    rulebook rules it cites, which is what makes the row checkable. A row citing
    only a section (`§5`) names nothing this can look up, and is reported as
    such rather than quietly passing.
    """

    blueprint_rows: tuple[str, ...]
    page: str
    rules: tuple[str, ...]
    section: str | None
    detail: str


def _normalise(raw: str) -> str:
    return raw.rstrip(".").split(",")[0].strip().lower()


def _rule_table_line_numbers(lines: list[str]) -> set[int]:
    """The 0-based indices of every row belonging to a rule table.

    A rule table is a `| # | Rule | Status |` header, its separator, and every
    line after it that starts a table cell. The run ends at the first line that
    does not — a blank line, a heading, a paragraph.
    """
    inside = False
    body: set[int] = set()
    for index, line in enumerate(lines):
        if _RULE_TABLE_HEADER.match(line):
            inside = True
            continue
        if not inside:
            continue
        if _TABLE_SEPARATOR.match(line):
            continue
        if not line.startswith("|"):
            inside = False
            continue
        body.add(index)
    return body


def orphan_rule_rows(directory: Path | None = None) -> list[str]:
    """Rows that look like rules but sit outside any rule table.

    The other half of a total parse. Requiring every row *inside* a rule table to
    parse cannot notice a whole table written with a different header — that
    table is simply invisible, and its rules go uncounted exactly as the lettered
    ones did. This looks from the other side: a bare rule id in a first cell
    belongs in a rule table, or the header is wrong.
    """
    orphans: list[str] = []
    for page in sorted((directory or RULEBOOK).glob("*.md")):
        lines = page.read_text(encoding="utf-8").splitlines()
        in_table = _rule_table_line_numbers(lines)
        for index, line in enumerate(lines):
            if index not in in_table and _ORPHAN_ROW.match(line):
                orphans.append(f"{page.name}:{index + 1}: {line.strip()[:100]}")
    return orphans


def parse_rules(directory: Path | None = None) -> list[Rule]:
    """Every rule in every rule table — or an exception naming the row that
    could not be read. Never a shorter list than the document states."""
    rules: list[Rule] = []
    for page in sorted((directory or RULEBOOK).glob("*.md")):
        lines = page.read_text(encoding="utf-8").splitlines()
        for index in sorted(_rule_table_line_numbers(lines)):
            line = lines[index]
            match = _ROW.match(line)
            if not match:
                raise RulebookParseError(
                    f"{page.name}:{index + 1} is a row of a `| # | Rule | Status |` "
                    f"table and does not parse as a rule:\n  {line.strip()[:200]}\n"
                    f"Every row of a rule table is a rule. Fix the row, or the "
                    f"table is not a rule table and needs a different header."
                )
            status_match = _STATUS.match(match["status"])
            status_raw = status_match["status"].strip() if status_match else ""
            rules.append(
                Rule(
                    id=match["id"],
                    page=page.name,
                    prefix=match["id"].split("-")[0],
                    status=_normalise(status_raw),
                    status_raw=status_raw,
                    text=match["text"],
                    evidence=tuple(
                        sorted(
                            {
                                token.strip()
                                for token in _BACKTICKED.findall(match["status"])
                                if _is_repo_path(token)
                            }
                        )
                    ),
                )
            )
    return sorted(rules, key=_order)


def _order(rule: Rule) -> tuple[str, int, str]:
    """`P-8a` sorts after `P-8` and before `P-9` — a lettered rule belongs beside
    the one it was added next to, which is why it is lettered."""
    match = _ID_ORDER.match(rule.id)
    assert match, rule.id
    return match["prefix"], int(match["number"]), match["suffix"]


def parse_deviations() -> list[Deviation]:
    """The **open** rows of §4 only.

    §4 carries two tables: the non-conformances that stand, and a "Closed since
    this table was last accurate" table kept so a reader who remembers a defect
    does not go looking for it. Reading both would report every closed row as an
    open one, so parsing stops at the second heading.
    """
    text = (RULEBOOK / "scope-and-deviations.md").read_text(encoding="utf-8")
    section = text.split("## 4. Known non-conformances", 1)[-1]
    section = section.split("**Closed since", 1)[0]

    deviations: list[Deviation] = []
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "| Row " in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        rows, stated_in, detail = cells[0], cells[1], cells[2]
        page = re.search(r"\]\((?P<page>[\w.-]+\.md)\)", stated_in)
        section_ref = re.search(r"§(?P<n>[\d.]+)", stated_in)
        deviations.append(
            Deviation(
                blueprint_rows=tuple(_BACKTICKED.findall(rows)),
                page=page["page"] if page else "",
                rules=tuple(re.findall(r"\b[A-Z]-\d+[a-z]?\b", stated_in)),
                section=section_ref["n"] if section_ref else None,
                detail=detail,
            )
        )
    return deviations


def build() -> dict:
    """The projection: every rule, indexed, plus the open non-conformances."""
    rules = parse_rules()
    return {
        "$comment": (
            "GENERATED from docs/rulebook/*.md by `task rulebook:generate`. "
            "The markdown is the source; edit that and regenerate."
        ),
        "statuses": list(STATUSES),
        "counts": {
            status: sum(r.status == status for r in rules) for status in STATUSES
        },
        "rules": [asdict(rule) | {"evidence": list(rule.evidence)} for rule in rules],
        "open_non_conformances": [
            asdict(d)
            | {"blueprint_rows": list(d.blueprint_rows), "rules": list(d.rules)}
            for d in parse_deviations()
        ],
    }


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def write() -> Path:
    PROJECTION.write_text(render(), encoding="utf-8")
    return PROJECTION
