# ADR-0005 — Knowledge mirrors the repository tree

**Date:** 2026-08-12
**Status:** superseded by [ADR-0002](ADR-0002-agent-material-is-not-committed.md)

Durable knowledge — the traps that are true of the code and not visible in it — is laid
out as a mirror of the repository tree, so the lookup rule for unit `X` is derived from
`X`'s own path rather than from a naming convention nobody can infer.

The layout is sound and is kept, in the companion, which now owns that material
(ADR-0002). This repository holds none of it.

`docs/services/*` is unaffected and must not converge with it: the published page says
what a unit does, for a reader; the companion says what will bite whoever edits it.
