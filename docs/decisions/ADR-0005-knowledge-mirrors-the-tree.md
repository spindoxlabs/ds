# ADR-0005 — Knowledge mirrors the repository tree

**Date:** 2026-08-12
**Status:** accepted

## Context

Repository knowledge — the traps that are true of the code and not visible in it — was
kept in `.agents/facts/`, laid out as a mirror of the repository:
`facts/services/connector.md`, `facts/libs/ds-auth.md`, `facts.md` for anything crossing
units. Around 1,900 lines, and by some distance the most useful prose in the repository.

The imported harness convention is a flat `.agents/knowledge/` directory, and its
conformance checker rejects any other subdirectory of `.agents/` by name — so `facts/`
reads as a violation.

The name and the layout are separable, and only one of them is load-bearing. The mirrored
layout answers "where is what I need to know about the unit I am editing?" with a path
derived from the unit's own path, which is the only lookup rule an agent can apply without
searching. Flattening it would replace that with a naming convention nobody can infer.

The name `facts/`, by contrast, is worth less than the interoperability of matching the
convention every other repository in this family uses — and it is slightly wrong: the
directory holds durable knowledge, of which "fact" is one shape.

## Decision

**The directory is `.agents/knowledge/` and the layout mirrors the repository tree.**

```text
.agents/knowledge/
    facts.md                     anything crossing units
    services/connector.md
    services/identity-registry.md
    libs/ds-auth.md
```

- A fact belongs to the unit that would have to **unlearn** it.
- Cross-unit facts — seams, the interaction between two units' assumptions — go in
  `knowledge/facts.md`, which keeps its name because it is a file, not a category.
- The move from `facts/` to `knowledge/` is a rename. No content is restructured, because
  the content was never the problem.

## Consequences

- Two references in `AGENTS.md` change; nothing else in the repository points at
  `.agents/facts/`.
- A conformance checker written against the flat convention will report the mirrored
  subdirectories. That is the checker's limitation, and it is stated here so the next
  person does not flatten the tree to make a tool quiet.
- The lookup rule is now uniform: for unit `X`, read `X/AGENTS.md` then
  `.agents/knowledge/X.md`. It holds for services and libs alike, and it extends to any
  unit added later without a decision.
- `knowledge/` and `docs/services/*` describe the same units and must not converge.
  `docs/services/*` says what the unit does and is published; `knowledge/` says what will
  bite you and is written for whoever edits it.
