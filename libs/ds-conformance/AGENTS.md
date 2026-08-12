# `libs/ds-conformance` — Agent Guide

## References

| What | Where |
|---|---|
| Building block | none — this unit implements no blueprint capability. It **measures** the rulebook against every one of them |
| Rules it states | none. It reports on all of them; it decides nothing |
| How it works, and its limits | [`docs/development/conformance.md`](../../docs/development/conformance.md) |
| What it produces | [`docs/rulebook/status.md`](../../docs/rulebook/status.md), generated and committed |

## Role and boundary

Answers *does this rulebook claim match the tests that exist* and *is every
binding blueprint row accounted for*, by reading files. It imports no service,
runs no suite and needs no stack.

**It reports; it never decides.** Every problem it raises is structural — a
claim with no referent, a referent that does not exist, a value outside a closed
set. It has no opinion about whether a rule is a good rule, and it must not
acquire one.

## Where things are

| File | Holds |
|---|---|
| `markdown.py` | the table scanner. Anchors on headers, and reports rows it cannot parse |
| `blueprints.py` | the requirement universe from `docs/blueprints/` |
| `rulebook.py` | the rules and the status each **claims**, from `docs/rulebook/` |
| `markers.py` | evidence, from four marker syntaxes across five test layers |
| `attribution.py` | rule→requirement links read off the rule's own text |
| `coverage.py` | `docs/rulebook/coverage.yaml` — the judgement calls only |
| `report.py` | the verdict truth table, and the page |
| `assess.py` | one entry point, so every command measures identically |

## Constraints that are not visible from the code

**Never read generated output back as input.** `status.md` lives in
`docs/rulebook/` and tabulates every rule id; parsing it doubled every rule and
reported each as stranded. `rulebook.GENERATED_PAGES` is the guard. Anything
this tool writes into a directory it also reads belongs in that set.

**Never swallow a parse error.** A file that will not parse must become a
`Problem`, never an empty result. A silent skip returns "this file evidences no
rule", which is indistinguishable from a file that genuinely declares none —
this unit reproduced that bug inside itself and hid thirteen broken flow files
behind a plausible zero. It is the failure mode the whole tool exists to expose.

**A row that does not parse under a known header is reported, not skipped.**
The scanner this replaced pattern-matched rows and missed nine lettered rules
(`P-8a`, `D-22b`, `X-6c`) for its entire life, under a guard reading `> 100`.
Anchor on the header; require every row beneath it.

**Do not assert a count.** `test_the_real_rulebook_parses_completely` asserts the
*property* — every rule-shaped row is inside a rule table and parsed. A floor
like `> 100` passes while rules are invisible and fails when work is completed.

**`Declared` owes no evidence, and must keep owing none.** Making it demand a
test would push authors to downgrade honest decisions, which inverts the
rulebook's honesty rule.

**`services/dataset-api-mock` is not evidence.** The root guide excludes it from
assessments. Nothing here should start counting it to make a number look better.

## Common tasks

| To | Do |
|---|---|
| Regenerate the page | `task rulebook:status` (from the repo root) |
| See why a rule reads as it does | `task rulebook:rule RULE=A-11` |
| Add a marker syntax | `markers.py`, plus a test proving a real-shaped source is read |
| Change what a verdict means | `report.judge` — the truth table is documented in the module docstring |

Every change carries unit tests, `ruff check` and `mypy --strict`, all of which
`task -d libs/ds-conformance lint` runs.
