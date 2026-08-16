# ADR-0002 — `.agents/` is committed; only `work/` is not

**Date:** 2026-08-12
**Status:** accepted

## Context

`.gitignore` excluded `.agents` in full. Everything an agent learned about this repository
— roughly 19,200 lines of per-unit facts, plans and defect rows — existed on one machine,
was never reviewed, and did not survive a clone.

Three costs were already being paid:

1. **Committed files cite identifiers whose definitions are ignored.** `DID-11`, `E2E-01`,
   `GOV-19` and their siblings appear around 400 times across 110 source and CI files and
   eight published documentation pages. Their definitions live only in the defect ledger,
   which nothing tracks. A reader of `docs/deployment/exposure.md` cannot look up
   `DID-11`.
2. **Nothing detects loss.** Within one morning the ledger moved paths twice and a plan's
   link to it broke. Neither event was visible to anyone, and no revert was possible.
3. **Review never happens.** The most consequential prose in the repository — why the
   obvious change is the wrong one — is the only prose that no pull request has ever
   shown.

The counter-argument is real: this repository is open source, and `.agents/` was written
under the assumption that it was private. It may name real organisations, sites or
datasets, which `AGENTS.md` forbids committing.

## Decision

**`.agents/` is committed. `.agents/work/` is not.**

```gitignore
.agents/work/
```

- `knowledge/`, `playbooks/`, `plans/`, `README.md` and `ledger.md` are repository
  artifacts, reviewed like any other file.
- `work/` holds execution state, which is transient by construction (ADR-0003) and would
  otherwise churn every commit.
- The publishing boundary in `AGENTS.md` applies to `.agents/` exactly as it applies to
  code, docs and fixtures.

**The flip is gated on a scrub pass.** No file that has never been reviewed against the
publishing boundary is committed on the strength of a grep alone; `knowledge/` and
`ledger.md` are read by a person first. The gate is a separate operation from the move, so
that it cannot be skipped by being bundled with one.

## Consequences

- A defect identifier cited in published documentation can be looked up in the same clone.
- `.agents/` changes appear in review, which is the point and also the cost: prose that
  used to be written freely now gets read.
- `work/` staying ignored preserves the property that makes the plan/work split cheap —
  progress can be written continuously without generating commits.
- The scrub is one-time for the existing content and continuous afterwards: it becomes
  part of the same publishing-boundary check that already applies to every other file.
- A future agent that writes a real deployment name into `knowledge/` now leaks it. That
  risk is accepted, and is the reason the boundary rule is restated in `AGENTS.md` under
  the `.agents/` heading rather than only under fixtures.
