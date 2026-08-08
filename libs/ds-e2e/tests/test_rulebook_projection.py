"""The rulebook is machine-readable, internally consistent, and not stale.

`DSSC-DSO-12` / rule `C-13` asks that metadata be checked against the rulebook.
It could not be, because **nothing read the document** — and the same absence had
a second cost that showed up first: on 2026-08-08 five of the ten rows in
`scope-and-deviations.md` §4 were already closed and the page still carried them,
every one understating the platform.

A compliance record that drifts silently is the artifact an assessor reads. These
assertions are what stops it drifting, and they are deliberately about the
*document*: the rulebook says what this dataspace decided, so a claim it makes
about a test that no longer exists, or a non-conformance whose rules are all
enforced, is a defect in the record itself.

**Why this lives here.** The invariant spans every page of `docs/rulebook/` and
belongs to no unit — the same argument `test_published_links_resolve.py` makes —
and `libs/ds-e2e` runs in CI. Offline by construction: it reads files, and this
suite refuses to open a socket at all (`tests/conftest.py`, `E2E-17`).
"""
from __future__ import annotations

import pytest

from ds_e2e.rulebook import (
    PROJECTION,
    STATUSES,
    RulebookParseError,
    orphan_rule_rows,
    parse_deviations,
    parse_rules,
    render,
    resolve_evidence,
)

RULES = parse_rules()
DEVIATIONS = parse_deviations()
BY_ID = {rule.id: rule for rule in RULES}

#: One rule id prefix per page. A rule's id says which page states it, so a `C-`
#: rule appearing under `policies.md` means a row was moved without renumbering
#: and two pages now claim the same authority.
PREFIX_BY_PAGE = {
    "catalogue-and-metadata.md": "C",
    "data-exchange.md": "X",
    "data-models.md": "M",
    "participation.md": "P",
    "personal-data.md": "D",
    "policies.md": "A",
    "provenance-and-logging.md": "L",
}

#: §4 rows that cite a *section* rather than rule ids, and legitimately so:
#: neither section states a numbered rule for the thing the row is about.
#: Declared rather than tolerated, so a row that starts citing a section to
#: escape the staleness check below has to be added here on purpose.
SECTION_ONLY_ROWS = {
    # Metadata versioning is discussed in the offering-lifecycle prose; §4 of
    # that page numbers rules about publication authority, not about versioning.
    ("DSSC-DSO-14", "-15"): ("catalogue-and-metadata.md", "4"),
    # "Observability — the open gap" carries no numbered rules at all, which is
    # itself the point: there is nothing yet to state as a rule.
    ("DSSC-PTO-03", "-42", "-46", "-57", "-63"): ("provenance-and-logging.md", "5"),
}


# ── Guard the guard ───────────────────────────────────────────────


#: The rulebook had this many rules when the projection was written. A floor
#: rather than an equality: rules get added, and that is not a failure.
#:
#: It is the *real* count, not a round "> 100", because "> 100" is what the
#: first version of this test said — and it passed at 128 while nine lettered
#: rules (`D-22a`, `P-8a`, `P-12b`, `X-6b`, …) were being dropped by a pattern
#: that ended at the digits. A guard whose threshold sits far below the true
#: number does not guard anything; it just looks like it does.
#:
#: It is now the *second* line of defence rather than the first: the parse is
#: total, so a row it cannot read raises instead of shrinking this number. This
#: catches the remaining case — rules deleted from the document — which should
#: be a deliberate edit here rather than a quieter compliance record.
KNOWN_RULE_COUNT = 137


def test_the_rulebook_parses():
    """A regex that quietly stopped matching would make every assertion below
    pass over an empty list — `E2E-01`'s `all([]) == True`, again."""
    assert len(RULES) >= KNOWN_RULE_COUNT, (
        f"only {len(RULES)} rules parsed from docs/rulebook/, expected at least "
        f"{KNOWN_RULE_COUNT}. Either the row pattern stopped matching some, or "
        f"rules were deleted — which is a deliberate edit to this constant, not "
        f"something a compliance record does by accident."
    )


def test_no_rule_row_sits_outside_a_rule_table():
    """The other half of a total parse.

    Requiring every row *inside* a `| # | Rule | Status |` table to parse cannot
    notice a whole table written with a different header — that table is simply
    invisible, and its rules go uncounted exactly as the lettered ones did.
    """
    orphans = orphan_rule_rows()
    assert not orphans, (
        "these rows look like rules but are not inside a rule table, so nothing "
        "counts them:\n  " + "\n  ".join(orphans)
    )


# ── The parse is total, and provably so ───────────────────────────
#
# These drive the parser against fixtures rather than the real rulebook. The
# assertions above say "the document parses today"; these say "a document that
# did not parse would be refused" — which is the actual property, and the one
# that was missing when nine lettered ids were dropped in silence.

RULE_TABLE = "| # | Rule | Status |\n|---|---|---|\n"


def _page(tmp_path, body: str):
    (tmp_path / "made-up.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_row_in_a_rule_table_that_does_not_parse_is_refused(tmp_path):
    """The failure mode a schema is usually reached for, closed without one.

    A row shaped in a way the pattern did not anticipate must stop the build,
    naming the page and line — not silently become "not a rule".
    """
    body = RULE_TABLE + "| C-1 | fine | **Enforced** |\n| ??? | odd |\n"
    page = _page(tmp_path, body)

    with pytest.raises(RulebookParseError) as exc:
        parse_rules(page)

    assert "made-up.md:4" in str(exc.value)


def test_a_lettered_row_parses(tmp_path):
    """`P-8a` is a rule. The pattern that ended at the digits said it was not,
    and nothing said otherwise for as long as it was wrong."""
    page = _page(tmp_path, RULE_TABLE + "| P-8a | lettered | **Enforced** |\n")

    assert [r.id for r in parse_rules(page)] == ["P-8a"]


def test_a_rule_table_with_the_wrong_header_is_found(tmp_path):
    """Not parsed — *found*. Its rows never reach `parse_rules`, so the only
    signal available is that they exist somewhere they should not."""
    page = _page(
        tmp_path,
        "| Id | Rule | State |\n|---|---|---|\n| C-1 | invisible | **Enforced** |\n",
    )

    assert parse_rules(page) == []
    assert orphan_rule_rows(page), "a mis-headed rule table went unnoticed"


def test_tables_that_are_not_rule_tables_are_left_alone(tmp_path):
    """The rulebook has 23 three-column tables that are not rules — the status
    markers, the standards list, the decide-and-record coverage. Reading those
    as rules would be the opposite failure, and just as wrong."""
    page = _page(
        tmp_path,
        "| Marker | Meaning |\n|---|---|\n| **Enforced** | code refuses it |\n\n"
        "| Row | Was | Now |\n|---|---|---|\n"
        "| `DSSC-AUP-13` | no version | emitted |\n",
    )

    assert parse_rules(page) == []
    assert orphan_rule_rows(page) == []


def test_lettered_rules_are_parsed():
    """A rule added beside an existing one is lettered so the numbering after it
    does not shift. They are the ids most likely to be dropped by a pattern
    written against the common case, and dropping them is invisible: the record
    simply says less than it does."""
    lettered = [rule.id for rule in RULES if rule.id[-1].isalpha()]
    assert len(lettered) >= 9, (
        f"only {lettered} parsed — lettered ids are being dropped"
    )
    assert len(DEVIATIONS) >= 5, (
        f"only {len(DEVIATIONS)} open non-conformances parsed from §4 — either "
        "the table shape changed or parsing stopped early"
    )


# ── The record is internally consistent ───────────────────────────


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_every_rule_declares_a_known_status(rule):
    """Four statuses, and no synonyms.

    `C-21` read **Partially enforced** while six other rules read **Partly
    enforced**. That is not a finer distinction — it is a value nobody could
    grep for, in the column an assessor filters on.

    A qualifier after a comma is prose and is kept: "Enforced, untested" and
    "Enforced, with a declared deviation" are both *enforced*.
    """
    assert rule.status in STATUSES, (
        f"{rule.id} ({rule.page}) declares status {rule.status_raw!r}, which is "
        f"not one of {list(STATUSES)}. Use one of those, with any nuance after a "
        f"comma."
    )


def test_rule_ids_are_unique():
    seen: dict[str, str] = {}
    duplicates = []
    for rule in RULES:
        if rule.id in seen:
            duplicates.append(f"{rule.id} in both {seen[rule.id]} and {rule.page}")
        seen[rule.id] = rule.page
    assert not duplicates, "\n".join(duplicates)


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_a_rules_prefix_matches_the_page_that_states_it(rule):
    expected = PREFIX_BY_PAGE.get(rule.page)
    assert expected is not None, (
        f"{rule.page} states rules but is not in PREFIX_BY_PAGE — a new rulebook "
        f"page needs an id prefix of its own"
    )
    assert rule.prefix == expected, (
        f"{rule.id} is stated in {rule.page}, whose rules are {expected}-*. A "
        f"rule moved between pages has to be renumbered, or two pages claim it"
    )


# ── The evidence it cites still exists ────────────────────────────

EVIDENCE = sorted({(rule.id, token) for rule in RULES for token in rule.evidence})


def test_there_is_evidence_to_check():
    assert len(EVIDENCE) > 10, (
        f"only {len(EVIDENCE)} evidence paths found across {len(RULES)} rules — "
        "the path heuristic is probably broken"
    )


@pytest.mark.parametrize(
    "rule_id,token", EVIDENCE, ids=[f"{rid}:{tok}" for rid, tok in EVIDENCE]
)
def test_cited_evidence_resolves_to_a_file(rule_id: str, token: str):
    """A status backed by a file that no longer exists is the drift with teeth.

    Renaming a test or moving a module is routine and nothing points back at the
    rulebook, so the claim outlives what backed it — and it is the *strongest*
    claims that rot this way, because only they cite anything.
    """
    assert resolve_evidence(token) is not None, (
        f"{rule_id} cites `{token}` as evidence and no such file exists. Either "
        f"re-point it at what backs the rule now, or the rule's status is no "
        f"longer true."
    )


# ── §4 agrees with the rules it cites ─────────────────────────────


@pytest.mark.parametrize(
    "deviation", DEVIATIONS, ids=["+".join(d.blueprint_rows) for d in DEVIATIONS]
)
def test_an_open_non_conformance_still_has_something_unkept(deviation):
    """§4 lists rules the code does **not** keep. If every rule a row cites is
    now `Enforced`, the row is closed and the page has not noticed.

    This is the exact failure of 2026-08-08, mechanised: the code moved, the
    compliance page did not, and it understated the platform to whoever read it.
    Closing a row means moving it to the "Closed since" table below, not deleting
    it — a reader who remembers the defect should not have to go looking.
    """
    if not deviation.rules:
        pytest.skip("cites a section; covered by the declared-list test")

    unknown = [r for r in deviation.rules if r not in BY_ID]
    assert not unknown, (
        f"§4 row {deviation.blueprint_rows} cites {unknown}, which no rulebook "
        f"page states"
    )

    statuses = {r: BY_ID[r].status for r in deviation.rules}
    assert any(status != "enforced" for status in statuses.values()), (
        f"§4 lists {deviation.blueprint_rows} as a known non-conformance, but "
        f"every rule it cites is now enforced: {statuses}. Move the row to "
        f"'Closed since this table was last accurate'."
    )


def test_the_rows_citing_only_a_section_are_exactly_the_declared_ones():
    """A row citing `§5` names nothing this can look up, so it is exempt from the
    staleness check above — which makes "cite a section" the way to opt out of
    being checked. Pinning the set means opting out is deliberate.

    If this fails because the set shrank, a row gained rule ids or was closed —
    drop it from `SECTION_ONLY_ROWS`. If it grew, a new row is unverifiable and
    needs either rule ids or an entry here saying why it has none.
    """
    found = {
        d.blueprint_rows: (d.page, d.section) for d in DEVIATIONS if not d.rules
    }
    assert found == SECTION_ONLY_ROWS


# ── The published projection is current ───────────────────────────


def test_the_projection_exists():
    assert PROJECTION.exists(), (
        f"{PROJECTION} missing — run `task rulebook:generate`"
    )


def test_the_projection_matches_regeneration():
    """`docs/rulebook/rules.json` is what "machine-readable" means for
    `DSSC-DSO-12`: the site serves it, so a check — ours or an assessor's — can
    read the rulebook without parsing nine markdown pages.

    It is generated, so it can go stale in the one way the markdown cannot.
    """
    assert PROJECTION.read_text(encoding="utf-8") == render(), (
        f"{PROJECTION} is stale — regenerate with `task rulebook:generate`"
    )
