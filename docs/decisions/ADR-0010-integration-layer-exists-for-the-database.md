# ADR-0010 — The integration layer exists because migrations run in no unit test

**Date:** 2026-08-12
**Status:** accepted
**Extracted from:** the header block of `.github/workflows/integration.yml`, which keeps
the code.

## Context

Every Python service builds its unit-test schema with `Base.metadata.create_all` against
SQLite in memory. That is the right choice for unit tests — it is fast, it needs no
service, and it keeps the layer honest about being about logic.

It has one consequence that is invisible from a green run: **the migrations run in no unit
test at all.** Eight revisions in the connector and three in provenance are executed by
nothing until a deployment executes them. A model changed without a revision keeps every
suite green and is found by whoever deploys next. Nor is any model ever exercised against
Postgres, so anything that differs between SQLite and Postgres — types, constraints,
transaction behaviour — is untested by construction.

`tests.yml` cannot close this. It runs the unit suites and nothing else, deliberately:
anything needing a live service costs more and belongs in a workflow with its own runtime.

## Decision

**A second CI workflow runs `test:integration` against real dependencies**, and its scope
is decided by what actually exists rather than by what would be tidy:

- Two jobs, because there are two dependencies — Postgres for the units with a database,
  and Keycloak for `libs/ds-auth` (ADR-0011).
- It lists **the units whose integration suite exists, passes, and needs only Postgres**. A
  `test:integration` task with nothing behind it is the `EDCL-10` shape — configuration for
  a suite that does not exist — and a job red on arrival is the `CI-01` shape, since a red
  `main` is how a workflow stops being read.
- Every step runs **the unit's own task**, never a hand-copied `pytest` line, so CI cannot
  drift from the local contract the root guide defines.

## Consequences

- `services/identity-registry` is the reason this workflow matters. Its integration suite is
  the oldest in the repository and had been **red** since `D-51` removed
  `ir-cli participant add` — nothing invoked it, so nothing said so. That is the `EDC-09` /
  `REV-01` pattern one layer out: a suite nobody runs is a suite that rots.
- That job starts **four uvicorn processes and takes ~45s**, against ~4s for the other two.
  Worth knowing before a slow job is mistaken for a hung one.
- The jobs override the `172.17.0.1` host-binding rule (ADR-0007) with a per-unit
  environment variable: on a laptop the Docker host gateway is right, and in CI the service
  container is published on localhost. The override is per-unit rather than global so a
  future suite can point at a different server.
- The database is waited for explicitly. `uv sync` is fast enough that the first
  `CREATE DATABASE` can arrive before Postgres accepts connections, and the race reads as a
  broken test.
- Adding a unit to this workflow is a claim that its integration suite passes. Make the
  claim only after running it.
