# ADR-0008 — `data/` is the only writable root

**Date:** 2026-08-12
**Status:** accepted
**Extracted from:** the root agent guide. This ADR states both the rule and the reason.

## Context

Generated, fetched and cached material was accumulating beside the thing that produced it
— `services/connector/governance-rec/vocab-cache` being the case that forced the decision.
Two problems, and the second is the one that compounds:

1. It mixed fetched state into a directory of committed configuration, where a `git status`
   can no longer distinguish "someone edited a profile" from "a process ran".
2. It added one more place to look for scratch data. That list grows one reasonable-looking
   exception at a time, and every entry has to be known by anyone cleaning a workspace,
   writing a `.gitignore`, or deciding whether a directory is safe to delete.

## Decision

**Anything a process writes, downloads or caches goes under `./data/<concern>/`, and
nowhere else.** `data/` is gitignored in full — nothing in it is tracked, not even a
`.gitkeep`, so a fresh clone has no `data/` and whatever needs a directory creates it.

| Existing | Holds |
|---|---|
| `data/gradle` | the EDC build's Gradle home |
| `data/caddy` | Caddy's config and state |
| `data/credentials` | per-role EDC credentials |
| `data/keys` | generated key material |
| `data/vocabularies` | fetched semantic vocabulary copies (`GET /ns/{slug}`) |

Four consequences follow, each of which has already been got wrong:

- **A setting that names a writable path defaults under `data/`**, and is added to
  `.env.example` in the same change like any other variable.
- **Committed configuration is not cache and does not move.** A registry, a profile or a
  governance file stays with its unit. Putting a committed file under `data/` deletes it
  from a fresh clone.
- **Compose mounts the specific subdirectory, never `./data` wholesale** — that directory
  also holds credentials and keys, which most services have no business seeing. The one
  exception is `data-dirs-init`, which exists to prepare them and reads nothing.
- **A bind-mounted `data/` subdirectory a container writes needs an entry in
  `data-dirs-init`.** A fresh clone has no `data/`, and Docker creates a missing bind-mount
  source **as root**, while every service runs as uid 10001 and cannot write what it was
  given (`TASK-10`).

## Consequences

- Cleaning a workspace is `rm -rf data/`, with no list to remember.
- The root `.gitignore` needs one entry for generated material rather than one per unit.
- Helm has `fsGroup` and needs none of this; the `data-dirs-init` container is a dev-only
  concession to compose having no equivalent. It is why forgetting an entry produces a
  container that will not start rather than one that degrades quietly — the loud failure
  is the design.
- The rule will be tested by the next cache that "obviously" belongs beside its unit. The
  answer is `data/`, and the reason is that the list stayed short.
