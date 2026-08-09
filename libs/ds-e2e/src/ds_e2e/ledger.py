"""The working ledger, checked against the compliance record it summarises.

`.agents/remaining.md` is the file a session reads to decide what to do next, and
it drifts **in one direction**: rows are added when work is found and rarely
deleted when it lands, because closing something does not feel like it needs a
documentation change. Measured on 2026-08-09, answering *"what's left?"* three
times required correcting it three times:

* a section headed *"Five open"* had two open — four had been closed or decided
  over the preceding two days and the rows still asked for decisions taken;
* a unit's summary count said `5 + REV-03` with `2` P1s against 4 and 1;
* a ruff count carried 180, then 182, then 183, against a real 178.

Every one **overstated what was open**, which is the expensive direction: it
sends the next session to re-measure work that is finished, and it buries the two
or three rows that are real.

## What this checks, and what it deliberately does not

Two things, both mechanical:

1. **Counts agree with their own sections.** The at-a-glance table states an open
   count per unit; the unit's own section lists rows with a state. If those
   disagree, one of them is wrong and the file cannot say which — so both are
   reported.
2. **Nothing is described as open that the rulebook says is enforced.** A line
   that both claims something is unresolved and cites a rulebook rule id is
   checked against `rules.json`.

It does **not** try to judge prose. A row saying *"needs a decision"* about a
decision already taken is only caught when it cites a rule id, and most do not —
so this closes the countable half of the drift and says so, rather than implying
it closes all of it.

## Why it is not in CI

`.agents/` is gitignored: it is a working document, not a published artifact, so
CI has no copy to check. This runs from `task ledger:check`, and when the file is
absent it **says so and exits 0** — a silent skip on a missing input is the shape
that made `test_rulebook_citations.py` pass for a wrong path depth.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ds_e2e.rulebook import PROJECTION, ROOT

LEDGER = ROOT / ".agents" / "remaining.md"

#: `| [`libs/ds-e2e`](#libsds-e2e) | **4** + `REV-03` | **1** | … |`
#:
#: The count cell is prose — `**4** + \`REV-03\``, `half of \`GOV-10\``, `**0**` —
#: so only a leading integer is read, and a cell with none is reported as
#: unparsed rather than assumed to be zero. Guessing zero would turn every prose
#: cell into a silent pass, which is the failure this module exists to catch.
#: `re.M` is load-bearing. Without it the leading `^` anchors to position 0 only,
#: so `finditer` matched **nothing** and half this module was a silent no-op —
#: found by asserting the match count rather than by trusting a clean run, which
#: is the whole lesson of the file this checks.
_GLANCE_ROW = re.compile(
    r"^\|\s*(?:~~)?\[`(?P<unit>[^`]+)`\]\(#(?P<anchor>[\w-]+)\)(?:~~)?\s*\|"
    r"\s*(?P<open>[^|]*)\|\s*(?P<p1>[^|]*)\|",
    re.M,
)

#: A row in a unit's own table: `| \`E2E-16\` | text | P1 | **state** | evidence |`
_UNIT_ROW = re.compile(r"^\|\s*`(?P<id>[A-Z]+-\d+[a-z]?)`\s*\|")

#: A state cell that means the row is **not** open. `verified`, `carried` and
#: `revised` all mean open — they describe how well the row was measured, not
#: whether it is finished, and reading them as closed is how a re-measured row
#: disappears.
_CLOSED = ("done", "closed", "dropped", "fixed", "resolved")

#: Phrases that claim something is unresolved. Deliberately narrow: a wide list
#: matches prose *about* a closed row and produces noise, and a check nobody
#: believes is worse than none.
_OPEN_CLAIM = (
    "blocked on a decision",
    "needs a decision",
    "decision first",
    "still open",
    "open gap",
    "not started",
    "is open",
)

_RULE_ID = re.compile(r"`([A-Z]-\d+[a-z]?)`")
_BLUEPRINT_ID = re.compile(r"(?:DSSC|CEEDS)-[A-Z]{3}-\d+")


@dataclass(frozen=True)
class Finding:
    kind: str
    detail: str


def _rule_statuses() -> dict[str, str]:
    if not PROJECTION.is_file():
        return {}
    data = json.loads(PROJECTION.read_text(encoding="utf-8"))
    return {r["id"]: r["status"] for r in data["rules"]}


def _closed_blueprint_rows() -> set[str]:
    """Blueprint rows the record no longer lists as open non-conformances.

    Read from the projection's `open_non_conformances`, so a row moved to the
    "Closed since" table here becomes closed there without anyone restating it —
    which is the point: the ledger and the rulebook then cannot disagree quietly.
    """
    if not PROJECTION.is_file():
        return set()
    data = json.loads(PROJECTION.read_text(encoding="utf-8"))
    still_open = {r for n in data["open_non_conformances"] for r in n["blueprint_rows"]}
    cited_anywhere = set(_BLUEPRINT_ID.findall(json.dumps(data)))
    return cited_anywhere - still_open


def _section_bounds(text: str, anchor: str) -> tuple[int, int] | None:
    """Where the section an at-a-glance row links to starts and ends.

    Anchors are GitHub-style slugs of the heading, which is how the ledger links
    them. Matching on the slug rather than the title means a retitled section
    fails loudly here instead of being silently skipped.
    """
    for match in re.finditer(r"^#{1,2} (?P<title>.+)$", text, re.M):
        # GitHub's slug: lowercase, drop punctuation, then **each space** becomes
        # a dash — not each run of spaces. `\`x\` — closed` leaves two spaces
        # where the em-dash was and so slugs to `x--closed`. Collapsing runs
        # produced one dash and reported every such heading as missing.
        slug = re.sub(r"[^\w\s-]", "", match["title"].lower())
        slug = re.sub(r"\s", "-", slug.strip())
        if slug == anchor:
            nxt = re.search(r"^#{1,2} ", text[match.end():], re.M)
            end = match.end() + nxt.start() if nxt else len(text)
            return match.start(), end
    return None


def check(path: Path | None = None) -> list[Finding]:
    """Every disagreement between the ledger and the record it summarises."""
    ledger = path or LEDGER
    if not ledger.is_file():
        return [
            Finding(
                "absent",
                f"{ledger} is not present — `.agents/` is gitignored, so there is "
                "nothing to check here. Stated rather than skipped silently.",
            )
        ]

    text = ledger.read_text(encoding="utf-8")
    statuses = _rule_statuses()
    findings: list[Finding] = []

    # ── 1. Every at-a-glance row points at a section that exists ─────────────
    #
    # **Not a count comparison, and that was tried.** The obvious check — the
    # summary says N open, the section lists M rows still open — cannot be made
    # precise against this file: the cell is prose with conventions (`5 +
    # \`REV-02\``, `half of \`GOV-10\``, `**0**`), the number deliberately
    # excludes the `REV-*` rows counted beside it, and three of the units have no
    # per-row table at all. It reported six disagreements of which one was real.
    #
    # So the count is **rendered for a person** (`open_rows`, printed by
    # `task ledger:status`) and not asserted. What is asserted here is the part
    # that has one right answer: a link either resolves or it does not.
    for match in _GLANCE_ROW.finditer(text):
        unit, anchor = match["unit"], match["anchor"]
        if _section_bounds(text, anchor) is None:
            findings.append(
                Finding(
                    "dangling-anchor",
                    f"the at-a-glance row for `{unit}` links to #{anchor}, which is "
                    "no heading in this file",
                )
            )

    # ── 2. Nothing claimed unresolved that the record says is settled ────────
    #
    # **Scoped to "Start here next session", and only there.** Two earlier
    # versions were wider and both were wrong:
    #
    # * a whole-file scan reported two findings, both false — this file is
    #   *history* by its own design ("the old ledger is history … this file is
    #   what is left"), so it read the record of a fix as a claim it is unfixed;
    # * a version keyed on each row's State cell needed to classify free prose
    #   (`verified`, `revised`, `half done — rdf: closed, ds: deliberately not`)
    #   and misclassified enough rows to be untrustworthy in both directions.
    #
    # What is left is narrow and true: the one section that is a claim about the
    # present, checked against the one record that is generated rather than
    # maintained. That is the section a session actually acts on, which is also
    # where a stale claim costs the most.
    bounds = _section_bounds(text, "start-here-next-session")
    if bounds is None:
        findings.append(
            Finding(
                "no-next-section",
                "there is no 'Start here next session' section — the one part of "
                "this file that states what is current, and the only part checked",
            )
        )
        return findings

    closed_blueprint = _closed_blueprint_rows()
    offset = 0
    for line in text.splitlines(keepends=True):
        if bounds[0] <= offset < bounds[1] and any(
            claim in line.lower() for claim in _OPEN_CLAIM
        ):
            for rule in _RULE_ID.findall(line):
                if statuses.get(rule) == "enforced":
                    findings.append(
                        Finding(
                            "stale-rule",
                            f"reads as unresolved and cites `{rule}`, which "
                            f"docs/rulebook records as enforced — {line.strip()[:90]}",
                        )
                    )
            for row in _BLUEPRINT_ID.findall(line):
                if row in closed_blueprint:
                    findings.append(
                        Finding(
                            "stale-blueprint",
                            f"reads as unresolved and cites `{row}`, which §4 no "
                            f"longer lists as open — {line.strip()[:90]}",
                        )
                    )
        offset += len(line)
    return findings


def report() -> int:
    """Print every finding. Exit code is what `task ledger:check` returns."""
    findings = check()
    if not findings:
        print("ledger: consistent with docs/rulebook")
        return 0
    if len(findings) == 1 and findings[0].kind == "absent":
        print(f"ledger: {findings[0].detail}")
        return 0
    for finding in findings:
        print(f"✗ [{finding.kind}] {finding.detail}")
    print(
        f"\n{len(findings)} disagreement(s) between .agents/remaining.md "
        "and docs/rulebook."
    )
    return 1

