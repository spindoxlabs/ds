"""`.agents/remaining.md` checked against the record it summarises.

Answering *"what's left?"* on 2026-08-09 required correcting that file three
times in one session, and every correction was in the same direction: it
**overstated what was open**. Rows are added when work is found and rarely
deleted when it lands.

These tests pin what the check can and cannot do, because two wider versions of
it were built first and both were wrong — and a check that reports closed work as
open would be switched off inside a week.
"""
from __future__ import annotations

import pathlib

import pytest

from ds_e2e.ledger import LEDGER, Finding, check

NEXT = "## Start here next session"


def _write(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    path = tmp_path / "remaining.md"
    path.write_text(body, encoding="utf-8")
    return path


def _kinds(findings: list[Finding]) -> set[str]:
    return {f.kind for f in findings}


# ── What it catches ───────────────────────────────────────────────────────────


def test_a_rule_the_rulebook_calls_enforced_cannot_be_called_open(tmp_path):
    """`C-13` sat in this file as *blocked on a decision* after it was closed."""
    path = _write(tmp_path, f"{NEXT}\n\n1. **`C-13`** is still open.\n")
    assert "stale-rule" in _kinds(check(path))


def test_a_blueprint_row_no_longer_in_section_4_cannot_be_called_open(tmp_path):
    """The ledger and the plan cite `DSSC-*` rows; §4 is the record of which are
    still open, and it is generated rather than maintained."""
    path = _write(tmp_path, f"{NEXT}\n\n- `DSSC-TRF-02` is an open gap.\n")
    assert "stale-blueprint" in _kinds(check(path))


def test_a_missing_next_section_is_itself_a_finding(tmp_path):
    """It is the only section checked, so losing it silently disables the check —
    the shape this whole module is about."""
    path = _write(tmp_path, "# Remaining\n\nnothing here\n")
    assert "no-next-section" in _kinds(check(path))


def test_a_dangling_at_a_glance_anchor_is_reported(tmp_path):
    path = _write(
        tmp_path,
        f"| [`libs/x`](#nowhere) | 1 | 0 | n |\n\n{NEXT}\n\nfine\n",
    )
    assert "dangling-anchor" in _kinds(check(path))


def test_an_em_dash_heading_resolves(tmp_path):
    """GitHub turns **each space** into a dash, so `\\`x\\` — closed` slugs with two.

    Collapsing runs of whitespace instead reported every such heading as missing,
    which was two false findings on the real file.
    """
    path = _write(
        tmp_path,
        f"| [`libs/x`](#libsx--closed-2026-08-06) | 0 | 0 | n |\n\n"
        f"{NEXT}\n\nfine\n\n# `libs/x` — closed 2026-08-06\n",
    )
    assert "dangling-anchor" not in _kinds(check(path))


# ── What it deliberately does not catch ───────────────────────────────────────


def test_history_elsewhere_in_the_file_is_not_a_claim(tmp_path):
    """Most of this file is a record of *closed* work by its own design.

    A whole-file scan produced two findings, both false: a closed `GOV-18` row
    whose prose contains "still open", and a `done 2026-08-06` row about
    DCAT-AP. Only the next-session section is a claim about the present.
    """
    path = _write(
        tmp_path,
        f"## Closed 2026-08-08\n\n| `GOV-18` | it was still open until now, `C-13` |\n\n"
        f"{NEXT}\n\nnothing outstanding\n",
    )
    assert check(path) == []


def test_no_count_is_asserted(tmp_path):
    """The summary cell is prose — `5 + \\`REV-02\\``, `half of \\`GOV-10\\`` — the
    number deliberately excludes the `REV-*` rows beside it, and three units have
    no per-row table at all.

    Comparing it to a derived row count reported six disagreements of which one
    was real, so it is **not** asserted. Recorded as a test because the obvious
    next idea is to add it back.
    """
    path = _write(
        tmp_path,
        f"| [`libs/x`](#libsx) | **99** | 0 | n |\n\n{NEXT}\n\nfine\n\n"
        f"# `libs/x`\n\n| `X-1` | a | P2 | **verified** | e |\n",
    )
    assert check(path) == []


# ── The absent case is stated, not skipped ────────────────────────────────────


def test_an_absent_ledger_is_reported_and_not_a_failure(tmp_path):
    """`.agents/` is gitignored, so CI has no copy. A silent pass on a missing
    input is what made `test_rulebook_citations.py` green on a wrong path."""
    findings = check(tmp_path / "not-here.md")
    assert [f.kind for f in findings] == ["absent"]


@pytest.mark.skipif(not LEDGER.is_file(), reason="working document, not in CI")
def test_the_real_ledger_is_consistent():
    """Runs where the file exists; the reason above is the file being gitignored,
    which is a fact about the repository rather than a way to avoid the check."""
    findings = check()
    assert findings == [], "\n".join(f"[{f.kind}] {f.detail}" for f in findings)
