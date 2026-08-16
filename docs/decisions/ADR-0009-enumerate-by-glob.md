# ADR-0009 — Iterate, never enumerate

**Date:** 2026-08-12
**Status:** accepted
**Extracted from:** comment blocks in `Taskfile.yml` (`build`, `edc:restart`) and
`.github/workflows/compliance.yml`, which keep the code.

## Context

The same defect has been paid for at least three times, in three files, by three different
mechanisms — each time because a task named the things it acted on instead of finding them:

- **`task build`** named the `rec` and `third-party` compose stacks. From `DID-15`, which
  added the grid operator as a second provider, a rebuild left that stack on its previous
  image while rebuilding the other two. The dataspace then ran half old code with every
  container healthy, and the stale half misbehaved only where the change was.
- **`edc:restart`** had the identical defect, and its fix was written in place — the same
  commit did not look at `build`.
- **`compliance.yml`** validated `governance-rec` alone while `governance-grid-operator`,
  a second producer published by the same platform into the same dataspace, was checked by
  nothing (`TASK-09`).

The failure mode is shared and it is quiet. A named list is correct on the day it is
written; it becomes wrong when someone adds a participant, a producer or a stack, and
nothing about that addition points at the file that needed editing. Every one of these was
found by a symptom somewhere else.

A second, related shape: **a loop that matches nothing must not succeed.** `compliance.yml`
would have exited 0 having validated nothing — the `all([]) == True` failure this
repository has already paid for twice (`E2E-01`, `CI-02`).

## Decision

**A task that acts on a set discovers that set; it does not list it.**

```bash
for f in ../../services/connector/governance-*/governance.yaml; do …; done
```

Three obligations come with it:

1. **Glob, don't name.** A participant, stack or producer added tomorrow is picked up
   without editing the task.
2. **An empty match is an error, not a success.** State how many things were found, and
   exit non-zero when the answer is none.
3. **A deliberate exclusion is stated in the file, with its reason.**
   `docker-compose.dataset-api.yml` is skipped by `task build` because it builds celine's
   sources from optional sibling checkouts — so on a machine without them the task would
   fail on somebody else's code. An unstated exclusion is indistinguishable from the bug.

Where a glob cannot express the set, a test asserts the coverage instead:
`libs/ds-e2e/tests/test_build_covers_every_stack.py` fails if a stack is skipped without
being declared.

## Consequences

- Adding a participant stops being a change that must be remembered in four places.
- CI jobs that fan out over units — `tests.yml`'s matrix, `integration.yml`'s — are the
  remaining named lists in the repository. They are named deliberately, because a matrix
  entry is also the thing that says a unit's suite exists and passes, and a glob there
  would turn a missing suite into a silent skip. **That exception is the reason the rule is
  written down rather than applied everywhere by reflex.**
- This is engineering hygiene with no blueprint referent, so it is an ADR and not a
  rulebook rule (ADR-0004). Nothing in `task rulebook:status` measures it; the test above
  measures the one case that could be tested cheaply.
