# ADR-0003 — Plans hold intent, work holds progress

**Date:** 2026-08-12
**Status:** superseded by [ADR-0002](ADR-0002-agent-material-is-not-committed.md)

Intent and position are two jobs with opposite lifetimes: what will change is durable,
where things stand is stale within a day. Kept in one document, the second rots the first
— every plan this repository held opened with a counts table that was already wrong.

The split is sound and is kept, in the store, which now owns both (ADR-0002). This
repository holds neither, so the decision has no referent here.

**What survives is the general rule, and it applies to committed files too: a number a
command can produce is never written down by hand.** State the exit criterion as the
command — `task rulebook:summary`, `task rulebook:unevidenced` — and let
[`docs/rulebook/status.md`](../rulebook/status.md) be the generated answer (ADR-0001).
