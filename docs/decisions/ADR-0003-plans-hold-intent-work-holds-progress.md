# ADR-0003 — Plans hold intent, `work/` holds progress

**Date:** 2026-08-12
**Status:** accepted

## Context

Every plan in this repository carried its own execution state inline, and every one of
them went stale between sessions:

- the compliance plan opened with *"Status as of 2026-08-08: 109 enforced · 21 declared ·
  7 partly · 1 not enforced, over 138 rules"* — and recorded, in the same paragraph, that
  the five numbers it previously stated were **all wrong**, because nine lettered rules
  had never been counted;
- the defect ledger opened with *"State as of 2026-08-09"* and a prose summary of which
  rows had closed;
- the conformance plan pinned itself to *"generated at `4e7bb62` (2026-08-10)"* and
  restated a twelve-row counts table that `task rulebook:summary` produces on demand.

The pattern is not carelessness. A plan is written once and read many times, so whoever
reads it wants to know where things stand — and the only place to write that, absent
somewhere better, is the plan. The document then has two jobs with opposite lifetimes: the
intent is durable and the position is stale within a day.

The repository had already found the general fix and applied it to conformance: derive the
number, do not assert it. `docs/rulebook/status.md` is generated and committed for exactly
this reason. What was missing was the same discipline for work in progress.

## Decision

**A plan and a work directory are one unit, sharing a slug, created together.**

```text
.agents/plans/<slug>.md   <->   .agents/work/<slug>/{status.md,notes.md}
```

- The **plan** holds intent: what will change, the decisions taken and why, deviations and
  why. It is committed.
- **`work/<slug>/status.md`** holds the position: progress, what was verified and how,
  blockers, owed work. It is not committed (ADR-0002).
- `work/<slug>/status.md` is created **before the first change of a phase**, not after it.
- A plan's phase status is derived from `status.md`. A phase status no `status.md` backs
  is a guess.
- **A measurement is never pasted into a plan.** The plan states the exit criterion as the
  command that produces the number — `task rulebook:summary`, `task rulebook:unevidenced`
  — and the number itself lives in `status.md`, where being stale is harmless.

## Consequences

- Plans get shorter and stop needing maintenance. A plan that names commands rather than
  counts is correct at every commit.
- The failure to catch becomes mechanical and cheap: **a plan marked `in-progress` with no
  `work/<slug>/status.md`**. The execution record is being written somewhere, and if not
  there then into the plan.
- Deleting a completed work directory is safe only after checking that every decision it
  records has moved into the plan or into `knowledge/`. That check is a step in the
  playbook, not a matter of memory.
- Existing plans convert by subtraction: front matter on, counts table out, exit criteria
  expressed as commands. The conformance plan is the first, because it is the one whose
  numbers move fastest.
- Someone will want the counts visible without running anything. That want is what
  `docs/rulebook/status.md` already serves — committed, generated, and diffable.
