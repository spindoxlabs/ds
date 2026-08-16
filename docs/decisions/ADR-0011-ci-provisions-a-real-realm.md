# ADR-0011 — CI provisions a real Keycloak realm rather than mocking it

**Date:** 2026-08-12
**Status:** accepted
**Extracted from:** the header block of `.github/workflows/integration.yml`, which keeps
the code.

## Context

`libs/ds-auth`'s integration suite needs a realm that has been **provisioned**, not merely
started. `realm-dataspaces-dev.json` carries only `oauth2_proxy` and six stock scopes —
every ds scope, service client and audience mapper is created afterwards by
`celine-policies keycloak sync`.

It was first assumed that made the suite un-runnable in CI, since the provisioning tool
belongs to the other repository. That assumption was wrong: the image is **public**, and
both inputs the sync needs are committed here. CI can perform exactly the same provisioning
step that `docker-compose.yml` performs, and then assert against the result.

The alternative — a mocked or hand-written realm fixture — checks that a realm *can* issue
tokens. That is not the interesting question. The question nothing else in the repository
covers is whether **the sync grants what `clients.yaml` declares**.

## Decision

**The `keycloak` job runs the real provisioning tool against a real Keycloak, and asserts
against the provisioned realm.**

The decision was measured both ways before it was written:

| Realm | Result |
|---|--:|
| provisioned by `celine-policies keycloak sync` | 13 passed |
| the same realm with the sync step skipped | 8 failed, 5 errors |

That asymmetry is the property being bought. A broken or absent sync turns this job **red**,
where a check that skips when its dependency is missing would turn it green by default —
which is the failure class this repository has paid for most often.

## Consequences

- The permission vocabulary has an end-to-end check: `clients.yaml` → sync → realm →
  `ds-auth`'s assertions. `libs/ds-auth/tests/test_vocabulary.py` covers the static half;
  this covers the half that only exists once something has applied it.
- CI depends on a public image from the celine side. If it stops being public, this job
  fails loudly rather than degrading, and the fallback is a fixture that answers a weaker
  question — which must then be stated in the job, not assumed.
- It is the only CI job that provisions anything. Anything else needing a live stack — the
  `e2e:*` flows, the portal's Playwright journeys — stays out of CI for cost reasons and is
  run locally against `task docker:restart`.
- No blueprint referent, so no rulebook rule (ADR-0004). What the realm must contain **is**
  rulebook material — see `P-8`, `P-8a` and the `libs/ds-auth` vocabulary rules — but that
  CI provisions it this way is an engineering decision.
