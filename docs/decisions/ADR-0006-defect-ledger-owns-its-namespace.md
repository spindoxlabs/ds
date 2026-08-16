# ADR-0006 — The defect ledger owns its identifier namespace

> **Superseded by ADR-0012.** The citation argument below holds — identifiers must
> resolve. Where they resolve to was wrong: defects are issues, and `.agents/ledger.md`
> is retired. Kept unedited otherwise, as the record of what was decided and why it
> changed.

**Date:** 2026-08-12
**Status:** superseded by [ADR-0012](ADR-0012-defects-are-issues.md)

## Context

This repository names its defects and workstreams, and then cites those names from
everywhere: `DID-11`, `E2E-01`, `GOV-19`, `TASK-10`, `CI-02`, `REV-04`, `EDC-09` and
their siblings appear around 400 times across 110 source and CI files, and in eight
published documentation pages — `docs/deployment/exposure.md` explains a host that stopped
existing "until `DID-11` step 2"; `.github/workflows/compliance.yml` explains an iteration
by naming the failure shape `TASK-09` fixed.

The citations are good practice. The problem is that nothing owned the other end:

- the ledger defining them was gitignored, so a reader of a published page could not look
  one up;
- it moved paths twice in one morning, breaking a link, with no diff to show it;
- it was named `remaining.md`, sat in `plans/`, and was flanked by a second file also
  about what remains — so which document defines `GOV-19` was itself a question;
- the bare `GOV-` prefix sits one hyphen away from `CEEDS-GOV-10`, a blueprint row
  identifier, in a repository where blueprint rows are cited the same way.

A defect row is also structurally unlike the other artifacts. It is not a plan (it states
a fact about the code, not an intention), not knowledge (it is meant to stop being true),
and not a rule (nothing measures it).

## Decision

**The ledger is `.agents/ledger.md`, it is committed, and it owns its identifiers.**

- One row per defect: what is wrong, and how to reproduce it.
- **Identifiers are permanent and never reused.** A closed row stays in the ledger, marked
  closed, because roughly 400 citations elsewhere resolve to it. Deleting a closed row
  breaks a comment in code that is still there.
- What to *do* about a set of defects is a plan (`.agents/plans/`), which cites the rows.
  The ledger does not hold remediation sequencing.
- Prefixes are the ones already in use. A new prefix is added to
  `.agents/knowledge/identifier-namespaces.md` in the same change that introduces it, so
  the count of namespaces stays known.

## Consequences

- A published page citing `DID-11` can be resolved from the same clone, by anyone.
- The `remaining.md` / `remaining-v2.md` ambiguity is resolved by kind rather than by
  version: `ledger.md` holds defects, `plans/conformance-closeout.md` holds the
  conformance workstreams. Their own headers had already argued for this split.
- Closed rows accumulate. That is the cost of permanent identifiers, and it is paid by
  sectioning the file rather than by pruning it.
- The near-collision between `GOV-` and `CEEDS-GOV-` stays. Renaming a prefix would
  invalidate every citation, which is exactly what permanent identifiers exist to prevent;
  the mitigation is documentation, in `identifier-namespaces.md`.
- The ledger is now published. A defect row that names a real deployment is a publishing
  boundary violation, which is one of the reasons ADR-0002 gates the commit on a scrub.
