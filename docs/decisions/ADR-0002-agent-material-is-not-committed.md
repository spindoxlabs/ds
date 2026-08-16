# ADR-0002 — Agent working material is not committed

**Date:** 2026-08-16
**Status:** accepted

## Context

This repository is open source. Agent working material — durable knowledge, playbooks,
plans and execution state — is written for whoever is building the platform, not for
whoever is reading it: it names the integration with the domain platform, the deployments
it was measured against, and the defects still open.

It was briefly committed here, on the argument that review and durability were worth the
exposure. They were not. The publishing boundary has to hold for every file it covers,
and prose written while working is the prose least likely to be checked against it.

## Decision

**Agent working material lives in a private companion repository, and never here.** The
companion is a parallel checkout outside this tree, excluded from version control on this
side.

| Content | Home |
|---|---|
| durable knowledge, playbooks, plans, execution state | the companion |
| why a technical choice was made | `docs/decisions/` |
| what this dataspace has decided about a blueprint obligation | `docs/rulebook/` |
| what a dataspace must implement | `docs/blueprints/` |
| how the system works, is built, run and deployed | `docs/` |
| what is broken | the issue tracker (ADR-0012) |

The companion's location differs per machine and is declared out of tree. Where it is not
to hand, ask for it — nothing agent-facing is written into this repository instead.

## Consequences

- What is committed is what is published. The publishing boundary covers one kind of file
  rather than two, and every file it covers is reviewed.
- Working material is not in the clone. It survives in the companion, which is where it
  is read from and the only source of truth for it.
- ADR-0003 and ADR-0005 governed how that material was organised in this repository. They
  no longer have a referent here and are superseded.
- Identifiers cited from committed code and documentation must resolve without it. That
  is what ADR-0012 requires of them.
