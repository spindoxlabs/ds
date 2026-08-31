"""Turn the assessment into the verdicts, and the verdicts into a page.

The verdict is the whole point of the tool. A rulebook status is a **claim**; a
verdict is that claim placed beside the tests that name the rule. The four
statuses and the evidence count give a small, closed truth table, and every cell
of it says something different:

| Claimed | Evidence | Verdict | Why it matters |
|---|---|---|---|
| Enforced / Partly | ≥1 | `evidenced` | the claim has a runnable referent |
| Enforced / Partly | 0 | **`unevidenced`** | the claim is prose. This is the finding |
| Declared | 0 | `consistent` | correct by definition — nothing could check it |
| Declared | ≥1 | `understated` | tests exist; the row may be upgradeable |
| Not enforced | 0 | `consistent` | claims nothing, owes nothing |
| Not enforced | ≥1 | **`contradicted`** | the row says no and the tree says yes |

`unevidenced` is not an accusation that a rule is unimplemented. It says the
repository cannot demonstrate the link, which is a different and more useful
statement — and it is the one the deleted `rules.json` could not make, because
it counted the claim rather than the referent.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .model import (
    DECLARED,
    ENFORCED,
    NOT_ENFORCED,
    PARTLY_ENFORCED,
    Assessment,
    Evidence,
    Force,
    Layer,
    Rule,
    State,
)
from .rulebook import sort_key


class Verdict(StrEnum):
    EVIDENCED = "evidenced"
    UNEVIDENCED = "unevidenced"
    CONSISTENT = "consistent"
    UNDERSTATED = "understated"
    CONTRADICTED = "contradicted"
    PRECEDENCE = "precedence"


#: Verdicts a reader should act on, in the order the report lists them.
ACTIONABLE: tuple[Verdict, ...] = (Verdict.UNEVIDENCED, Verdict.CONTRADICTED, Verdict.UNDERSTATED)


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    rule: Rule
    verdict: Verdict
    evidence: tuple[Evidence, ...]

    @property
    def by_layer(self) -> Counter[str]:
        return Counter(e.layer.value for e in self.evidence)


def judge(rule: Rule, evidence: list[Evidence]) -> RuleVerdict:
    count = len(evidence)
    ordered = tuple(sorted(evidence, key=lambda e: (e.layer.value, e.file, e.line)))

    if rule.status is None:
        # A `| # | Rule | Source |` row: it states precedence and cites the
        # blueprint row it comes from. Enforcement is asserted elsewhere.
        verdict = Verdict.PRECEDENCE
    elif rule.status in (ENFORCED, PARTLY_ENFORCED):
        verdict = Verdict.EVIDENCED if count else Verdict.UNEVIDENCED
    elif rule.status == DECLARED:
        verdict = Verdict.UNDERSTATED if count else Verdict.CONSISTENT
    elif rule.status == NOT_ENFORCED:
        verdict = Verdict.CONTRADICTED if count else Verdict.CONSISTENT
    else:
        verdict = Verdict.UNEVIDENCED

    return RuleVerdict(rule=rule, verdict=verdict, evidence=ordered)


def judge_all(assessment: Assessment) -> list[RuleVerdict]:
    return [judge(rule, assessment.evidence_for(rule.id)) for rule in assessment.rules]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


# ── Provenance, which is not measurement ──────────────────────────
#
# `status.md` opens with a line naming the commit the page was rendered at. It
# is the one line on the page that is *about* the page rather than about the
# tree, and `--check` must not compare it: the page is committed, so the render
# always happens before the commit that carries it, and the line therefore names
# the parent commit forever. Writing the page also dirties the tree, so a
# re-render at the same HEAD says `X-dirty` against the `X` on disk. Comparing
# it makes `--check` unsatisfiable in both directions — it was red in every
# commit that has ever carried the page.
#
# The regex lives beside `_provenance`, which writes the line, so the writer and
# the stripper cannot drift into comparing nothing.

#: Matches exactly what `_provenance` emits, and nothing else on the page.
PROVENANCE_RE = re.compile(r"^Generated \d{4}-\d{2}-\d{2} from `[^`]*`\.$", re.MULTILINE)


def _provenance(generated_on: date, commit: str) -> str:
    return f"Generated {generated_on.isoformat()} from `{commit}`."


def measurement_of(page: str) -> str:
    """`page` with its provenance line blanked — the part `--check` compares.

    Blanked rather than deleted so both sides keep the same line numbering, and
    so a page that somehow carries no provenance line is still comparable.
    """
    return PROVENANCE_RE.sub("", page)


def _cite(item: Evidence) -> str:
    return f"`{item.node}`"


def _evidence_cell(verdict: RuleVerdict, limit: int = 3) -> str:
    if not verdict.evidence:
        return "—"
    shown = ", ".join(_cite(e) for e in verdict.evidence[:limit])
    remaining = len(verdict.evidence) - limit
    return f"{shown} +{remaining} more" if remaining > 0 else shown


def _mark(verdict: Verdict) -> str:
    return {
        Verdict.EVIDENCED: "✅ evidenced",
        Verdict.UNEVIDENCED: "❌ **unevidenced**",
        Verdict.CONSISTENT: "· consistent",
        Verdict.UNDERSTATED: "⬆ understated",
        Verdict.CONTRADICTED: "⚠ **contradicted**",
        Verdict.PRECEDENCE: "· precedence",
    }[verdict]


def render(assessment: Assessment, *, generated_on: date, commit: str) -> str:
    verdicts = judge_all(assessment)
    by_id = {v.rule.id: v for v in verdicts}
    counts = Counter(v.verdict for v in verdicts)
    claiming = [v for v in verdicts if v.rule.claims_enforcement]
    evidenced = [v for v in claiming if v.verdict is Verdict.EVIDENCED]

    out: list[str] = []
    w = out.append

    w("# Conformance status")
    w("")
    w(
        "**Generated. Do not edit.** `task rulebook:status` rewrites this file from "
        "`docs/blueprints/`, `docs/rulebook/`, the coverage manifest and the test "
        "sources. It is committed so that drift shows up in a diff."
    )
    w("")
    w(_provenance(generated_on, commit))
    w("")
    w(
        "This page measures **linkage**, not correctness. A rule is *evidenced* when a "
        "test node names it — not when that node passes. Whether the suite is green is "
        "the runner's answer; see `docs/development/testing.md`. What this page can say, "
        "and no hand-written status can, is whether a claim has a runnable referent at all."
    )
    w("")

    # ---- headline -------------------------------------------------------
    w("## Where the platform stands")
    w("")
    w("| Measure | Count |")
    w("|---|--:|")
    w(f"| Blueprint requirement rows | {len(assessment.requirements)} |")
    binding = [r for r in assessment.requirements if r.is_binding]
    w(f"| …of which binding (`must` + `should`) | {len(binding)} |")
    dispositioned = sum(
        1
        for r in binding
        if r.id in assessment.dispositions
        and assessment.dispositions[r.id].state is not State.UNASSESSED
    )
    w(f"| …carrying a disposition | {dispositioned} |")
    strong = sum(
        1
        for r in binding
        if (d := assessment.dispositions.get(r.id)) and d.state is State.COVERED and d.rules
    )
    weak = sum(
        1
        for r in binding
        if (d := assessment.dispositions.get(r.id))
        and d.state is State.COVERED
        and not d.rules
        and d.pages
    )
    w(f"| …answered by a **named rule** | {strong} |")
    w(f"| …answered **at page level only** | {weak} |")
    w(f"| …**unassessed** | {len(binding) - dispositioned} |")
    w(f"| Rulebook rules | {len(assessment.rules)} |")
    w(f"| …claiming enforcement (`Enforced` / `Partly enforced`) | {len(claiming)} |")
    w(f"| …of those, **evidenced by a test that names them** | {len(evidenced)} |")
    w(f"| …of those, **unevidenced** | {counts[Verdict.UNEVIDENCED]} |")
    w(f"| Test nodes declaring a rule | {len(assessment.evidence)} |")
    w(f"| Structural problems | {len(assessment.problems)} |")
    w("")

    if claiming:
        share = 100 * len(evidenced) / len(claiming)
        w(
            f"**{share:.0f}% of the rules that claim enforcement can name a test.** "
            "That number is the one to move."
        )
        w("")

    # ---- the finding ----------------------------------------------------
    w("## Rules claiming enforcement with no test naming them")
    w("")
    unevidenced = [v for v in verdicts if v.verdict is Verdict.UNEVIDENCED]
    if not unevidenced:
        w("None. Every rule claiming enforcement names at least one test node.")
    else:
        w(
            f"{len(unevidenced)} rules. Each says the code refuses a violating case and "
            "no test declares itself as the check. Either a marker is missing from a test "
            "that already exists, or the check does."
        )
        w("")
        w("| Rule | Page | Claim | Statement |")
        w("|---|---|---|---|")
        for verdict in sorted(unevidenced, key=lambda v: sort_key(v.rule.id)):
            statement = _truncate(verdict.rule.statement, 90)
            w(
                f"| `{verdict.rule.id}` | {verdict.rule.page} "
                f"| {verdict.rule.status} | {statement} |"
            )
    w("")

    contradicted = [v for v in verdicts if v.verdict is Verdict.CONTRADICTED]
    if contradicted:
        w("## Rules the tree contradicts")
        w("")
        w("The row says the platform does not keep the rule; a test says it does.")
        w("")
        w("| Rule | Page | Tests naming it |")
        w("|---|---|---|")
        for verdict in sorted(contradicted, key=lambda v: sort_key(v.rule.id)):
            w(f"| `{verdict.rule.id}` | {verdict.rule.page} | {_evidence_cell(verdict)} |")
        w("")

    understated = [v for v in verdicts if v.verdict is Verdict.UNDERSTATED]
    if understated:
        w("## Rules that may be understated")
        w("")
        w(
            "Marked `Declared` — a decision nothing could check — yet tests name them. "
            "Either the marker is on the wrong rule, or the row has become enforceable "
            "and nobody updated it."
        )
        w("")
        w("| Rule | Page | Tests naming it |")
        w("|---|---|---|")
        for verdict in sorted(understated, key=lambda v: sort_key(v.rule.id)):
            w(f"| `{verdict.rule.id}` | {verdict.rule.page} | {_evidence_cell(verdict)} |")
        w("")

    # ---- per rule -------------------------------------------------------
    w("## Every rule, by page")
    w("")
    for page in sorted({v.rule.page for v in verdicts}):
        page_verdicts = [v for v in verdicts if v.rule.page == page]
        w(f"### `{page}.md`")
        w("")
        w("| Rule | Claimed | Verdict | Layers | Evidence |")
        w("|---|---|---|---|---|")
        for verdict in sorted(page_verdicts, key=lambda v: sort_key(v.rule.id)):
            layers = (
                ", ".join(f"{name}×{n}" for name, n in sorted(verdict.by_layer.items()))
                if verdict.evidence
                else "—"
            )
            claimed = verdict.rule.status or "—"
            w(
                f"| `{verdict.rule.id}` | {claimed} | {_mark(verdict.verdict)} "
                f"| {layers} | {_evidence_cell(verdict)} |"
            )
        w("")

    # ---- blueprint coverage --------------------------------------------
    w("## Blueprint coverage")
    w("")
    w(
        "Every binding blueprint row and what answers it. `may` and `recommended` rows "
        "are counted below but never demand a disposition — declining an optional row "
        "owes nobody an explanation, silently dropping a `must` owes everybody one."
    )
    w("")
    w("| Prefix | Binding rows | covered | open | out-of-scope | unassessed |")
    w("|---|--:|--:|--:|--:|--:|")
    prefixes = sorted({_prefix(r.id) for r in assessment.requirements})
    for prefix in prefixes:
        rows = [r for r in assessment.requirements if _prefix(r.id) == prefix and r.is_binding]
        if not rows:
            continue
        tally: Counter[State] = Counter()
        for row in rows:
            entry = assessment.dispositions.get(row.id)
            tally[entry.state if entry else State.UNASSESSED] += 1
        w(
            f"| `{prefix}` | {len(rows)} | {tally[State.COVERED]} | {tally[State.OPEN]} "
            f"| {tally[State.OUT_OF_SCOPE]} | {tally[State.UNASSESSED]} |"
        )
    w("")

    non_binding = [r for r in assessment.requirements if not r.is_binding]
    w(f"Non-binding rows not shown above: {len(non_binding)} ({_force_summary(assessment)}).")
    w("")

    covered = {rid: d for rid, d in assessment.dispositions.items() if d.state is State.COVERED}
    by_requirement = {r.id: r for r in assessment.requirements}
    named = {rid: d for rid, d in covered.items() if d.rules}
    page_only = {rid: d for rid, d in covered.items() if not d.rules and d.pages}

    if named:
        w("### Rows answered by a named rule")
        w("")
        w(
            "The strong form: the row inherits its rule's verdict, so a rule nothing "
            "tests makes the row visibly unanswered rather than quietly done."
        )
        w("")
        w("| Requirement | Force | Rules | From | Every rule evidenced? |")
        w("|---|---|---|---|---|")
        for requirement_id in sorted(named):
            disposition = named[requirement_id]
            requirement = by_requirement.get(requirement_id)
            if requirement is None:
                continue
            rules = ", ".join(f"`{r}`" for r in disposition.rules)
            origin = "rule text" if disposition.derived else "manifest"
            verdicts_for = [by_id[r] for r in disposition.rules if r in by_id]
            claiming_here = [v for v in verdicts_for if v.rule.claims_enforcement]
            if not claiming_here:
                answer = "n/a — declared"
            elif all(v.verdict is Verdict.EVIDENCED for v in claiming_here):
                answer = "yes"
            else:
                missing = [v.rule.id for v in claiming_here if v.verdict is not Verdict.EVIDENCED]
                answer = "**no** — " + ", ".join(f"`{m}`" for m in missing)
            w(f"| `{requirement_id}` | {requirement.force.value} | {rules} | {origin} | {answer} |")
        w("")

    if page_only:
        w("### Rows answered only at page level")
        w("")
        w(
            f"{len(page_only)} rows. A rulebook page addresses the topic and nobody has "
            "said which rule answers the row, so no evidence attaches and none of these "
            "can read as done. This is the granularity the rulebook's own *Blueprint "
            "rows* sections have; sharpening one to a named rule is the work."
        )
        w("")
        w("| Requirement | Force | Page | Requirement text |")
        w("|---|---|---|---|")
        for requirement_id in sorted(page_only):
            disposition = page_only[requirement_id]
            requirement = by_requirement.get(requirement_id)
            if requirement is None:
                continue
            pages = ", ".join(f"[{name}]({name}.md)" for name in disposition.pages)
            w(
                f"| `{requirement_id}` | {requirement.force.value} | {pages} "
                f"| {_truncate(requirement.text, 90)} |"
            )
        w("")

    open_rows = {rid: d for rid, d in assessment.dispositions.items() if d.state is State.OPEN}
    if open_rows:
        w("### Binding rows accepted and not met")
        w("")
        w("| Requirement | Force | What is missing |")
        w("|---|---|---|")
        for requirement_id in sorted(open_rows):
            requirement = by_requirement.get(requirement_id)
            if requirement is None:
                continue
            w(
                f"| `{requirement_id}` | {requirement.force.value} "
                f"| {open_rows[requirement_id].note} |"
            )
        w("")

    declined = {
        rid: d for rid, d in assessment.dispositions.items() if d.state is State.OUT_OF_SCOPE
    }
    if declined:
        w("### Binding rows deliberately declined")
        w("")
        w(
            "Each belongs in [Scope and deviations](scope-and-deviations.md) as well; "
            "this table is the index, that page is the argument."
        )
        w("")
        w("| Requirement | Force | Reason |")
        w("|---|---|---|")
        for requirement_id in sorted(declined):
            requirement = by_requirement.get(requirement_id)
            if requirement is None:
                continue
            w(
                f"| `{requirement_id}` | {requirement.force.value} "
                f"| {declined[requirement_id].note} |"
            )
        w("")

    # ---- problems -------------------------------------------------------
    w("## Structural problems")
    w("")
    if not assessment.problems:
        w("None.")
    else:
        w(
            "Each is a claim with no referent, a referent that does not exist, or a value "
            "outside a closed set. None is an opinion about whether a rule is a good rule."
        )
        w("")
        w("| Kind | Subject | Detail | Where |")
        w("|---|---|---|---|")
        for problem in sorted(assessment.problems, key=lambda p: (p.kind, p.subject, p.where)):
            w(
                f"| `{problem.kind}` | `{problem.subject}` "
                f"| {_truncate(problem.detail, 140)} | {problem.where} |"
            )
    w("")

    # ---- how to move it -------------------------------------------------
    w("## Moving a row")
    w("")
    w("**To evidence a rule**, put the marker on the test that already checks it:")
    w("")
    w("```python")
    w('@pytest.mark.rule("A-11")')
    w("def test_sustained_silence_denies() -> None: ...")
    w("```")
    w("")
    w("```java")
    w('@Test @Tag("rule:A-11")')
    w("void sustainedSilenceDenies() { … }")
    w("```")
    w("")
    w("```python")
    w("class ConsentWithdrawalFlow(Flow):     # libs/ds-e2e/src/ds_e2e/flows/")
    w('    rules = ("D-17", "CR-5")')
    w("```")
    w("")
    w("```ts")
    w("test('a viewer cannot write @rule:P-12', async ({ page }) => { … })")
    w("```")
    w("")
    w(
        "**If no such test exists**, that is the finding — write the check, or change the "
        "row to say what is true. The honesty rule allows exactly four markers and "
        "`Declared` is an honourable one."
    )
    w("")
    w("**To disposition a blueprint row**, add it to `docs/rulebook/coverage.yaml`:")
    w("")
    w("```yaml")
    w("dispositions:")
    w("  DSSC-AUP-01:")
    w("    state: covered            # covered | open | out-of-scope | unassessed")
    w("    rules: [A-3, A-4]")
    w("  DSSC-AUP-06:")
    w("    state: open")
    w("    note: the validity window needs a date operand bound in the EDC first")
    w("```")
    w("")

    return "\n".join(out) + "\n"


def _prefix(requirement_id: str) -> str:
    return "-".join(requirement_id.split("-")[:2])


def _force_summary(assessment: Assessment) -> str:
    tally = Counter(r.force for r in assessment.requirements if not r.is_binding)
    return ", ".join(
        f"{tally[force]} {force.value}"
        for force in (Force.RECOMMENDED, Force.MAY, Force.INFORMATIVE, Force.OTHER)
        if tally[force]
    )


def _truncate(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def summarise(assessment: Assessment) -> dict[str, int]:
    """The counts, for a terminal line and for a test to assert on."""
    verdicts = judge_all(assessment)
    counts = Counter(v.verdict for v in verdicts)
    binding = [r for r in assessment.requirements if r.is_binding]
    return {
        "requirements": len(assessment.requirements),
        "binding": len(binding),
        "rules": len(assessment.rules),
        "claiming": sum(1 for v in verdicts if v.rule.claims_enforcement),
        "evidenced": counts[Verdict.EVIDENCED],
        "unevidenced": counts[Verdict.UNEVIDENCED],
        "contradicted": counts[Verdict.CONTRADICTED],
        "understated": counts[Verdict.UNDERSTATED],
        "evidence_nodes": len(assessment.evidence),
        "problems": len(assessment.problems),
        "unassessed": sum(
            1
            for r in binding
            if assessment.dispositions.get(r.id) is None
            or assessment.dispositions[r.id].state is State.UNASSESSED
        ),
    }


__all__ = [
    "Verdict",
    "RuleVerdict",
    "judge",
    "judge_all",
    "measurement_of",
    "render",
    "summarise",
    "Layer",
]
