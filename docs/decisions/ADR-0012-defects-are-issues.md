# ADR-0012 — Defects are issues, not a repository artifact

**Date:** 2026-08-12
**Status:** accepted
**Supersedes:** ADR-0006

## Context

ADR-0006 gave the defect ledger a home in `.agents/ledger.md` and a namespace of its own,
on the reasoning that roughly 400 citations from committed code and documentation had to
resolve somewhere. That solved the citation problem and left the modelling problem
untouched, which is the one that mattered.

The knowledge contract models intent (`plans/`), procedure (`playbooks/`), durable truth
(`knowledge/`) and position (`work/`). A defect is none of them:

- **It is not a plan.** A plan is intent; a defect row is an observation that exists before
  anyone decides to act on it. The ledger's own history proves the gap matters — `KC-05`,
  `TASK-08` and `O2P-03` were **dropped**, three keycloak rows turned out to rest on a false
  premise when re-measured, and nine rows across two units were declined outright. None
  became work. If every defect needed a plan, plans would have been written for things that
  were then declined.
- **It is not knowledge.** Knowledge is what should *stay* true; a defect is what should
  *stop* being true. Same tense, opposite intent.
- **It is not work.** `work/` is the execution state of one plan and dies with it.

What a defect actually carries is a lifecycle — open, closed, dropped — plus a priority, an
owner and a permanent identifier. That is an issue tracker, and `ledger.md` had become one:
1,300 lines that were three documents at once (a session journal, a closed-work narrative,
and the rows), with a 5,754-line companion. The granularity confirms it — one defect never
mapped to one plan; a themed plan cited dozens of rows and drew from the ledger as a queue.

## Decision

**Defects are issues, in the project's issue tracker, and `.agents/` does not model them.**

`.agents/ledger.md` is retired. Its content goes three ways:

| Content | Destination |
|---|---|
| A row still open | an issue |
| A row that violates a rulebook rule | an issue **and** the rulebook — `coverage.yaml` `open`, or the rule reading *Not enforced*. The issue is the work; the rulebook row is the measurement (ADR-0001) |
| A lesson — "the wrong turn, recorded because the next reader will take it too" | `.agents/knowledge/` |
| A closed row, and the session journal | deleted. An issue that is closed is closed |

A plan cites the issues it closes; `work/<slug>/status.md` names which ones a phase
actually closed. Neither restates the issue.

### Identifiers

The issue number **is** the identifier — permanent, resolvable by anyone with the
repository, and incapable of colliding with a rulebook rule or a blueprint row. The invented
prefixes (`GOV-`, `E2E-`, `DID-`, `P0-`…) are retired: they exist only in git history and in
prose that no longer needs them.

### How an agent resolves or files one

**Use the forge's own tooling.** On GitHub that is `gh`:

```bash
gh issue view 123
gh issue list --state open --label defect
gh issue create --title "…" --body "…"
```

Any equivalent automation for another forge is fine. **Where no such tooling is available —
no CLI, no credentials, no network — do not invent an identifier and do not reintroduce a
ledger file. Write a plain reference instead:** state the defect in prose where it matters,
and say that it is unfiled. A named thing that cannot be looked up is worse than an
unnamed one, which is the whole lesson of the retired namespaces.

### What a code comment carries

**The prose, not the number.** A comment reads:

```python
# `auto_discover` was removed here. It guessed a `governance.yaml` path …
```

and may end with `(#123)`. The sentence has to survive the number being unresolvable,
because issues are not in the clone.

## Consequences

- The knowledge contract stops needing a fifth artifact for a class it was never designed
  to hold. This is the harness shrinking rather than growing.
- **Issues are not in the clone.** An agent working offline cannot read `#123`. That is the
  exact failure ADR-0002 exists to prevent, and the mitigation is the comment rule above:
  the reason lives in the tree, the state lives in the tracker. It is a real cost, accepted
  deliberately, and it is why an unresolvable *number* is tolerable where an unresolvable
  *namespace* was not.
- The project does not currently use issues — no templates, nothing filed. Adopting this
  means filing the still-open rows once, from a reviewed list, rather than bulk-importing
  a thousand lines of history.
- **The deterministic list stays deterministic.** Anything with a rulebook referent is
  still measured by `task rulebook:status`; the issue tracker never becomes a second answer
  to "what is missing". Where the two would disagree, the rulebook wins and the issue is
  wrong.
- ADR-0006's citation argument was correct and is preserved: identifiers must resolve. The
  correction is *where* they resolve to.
