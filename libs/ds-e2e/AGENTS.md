# ds-e2e

The `ds-e2e` CLI. Seventeen named **flows**, each a class making a sequence of live HTTP calls
against a running stack and recording a `Step` per assertion. Plus a declarative fixture
provisioner (`ds-e2e scenario`), a destructive state reset (`ds-e2e clean`) and a
reachability probe (`ds-e2e health`).

Nothing in the platform imports it; it is invoked from the root `Taskfile.yml`.

**This is the only harness that exercises the real DSP exchange**, so its blind spots are the
platform's.

## References

| | |
|---|---|
| Requirements | it verifies all of them — start from [docs/blueprints/index.md](../../docs/blueprints/index.md) |
| Rules | [docs/rulebook/](../../docs/rulebook/index.md) — a flow should assert a rulebook rule, and the rule should name the flow |
| Code as committed | [docs/services/libs/ds-e2e.md](../../docs/services/libs/ds-e2e.md) · [docs/development/running-the-stack.md](../../docs/development/running-the-stack.md) |

## Flow aggregates

`--flow all` · `--flow fast` (everything that runs without the EDC) · `--flow security`
(`api-contract`, `authz-perimeter`, `dcp-trust`) · `--flow chains` (the three delegation
chains). **`fast` is the set to run on every change** — it needs only ds-connector,
identity-registry, provenance, federated-catalog and Keycloak.

The per-flow inventory is `docs/services/libs/ds-e2e.md`; the registry is
`flows/__init__.py`.

## Writing an assertion

Use `http.raw(method, url, ...)`, which returns `(status, payload)` and never raises —
`http.get`/`post` raise on 4xx, which is the wrong shape when the 4xx *is* the assertion.

Four rules the security flows follow, and new ones should too:

- **A refusal must be a 4xx, not a 5xx.** A guard that raises has let the request reach
  application code before authorisation was settled; the fix is different, so the flows treat
  it as a distinct failure class from "allowed".
- **A skip must be loud.** When a precondition is missing, pass the step with the reason in
  its detail rather than asserting nothing. A security assertion that quietly became a no-op
  is worse than one that was never written.
- **A refusal probe needs an otherwise-valid body.** If the payload would also fail schema
  validation, the probe passes on a 422 with the guard deleted. `ds_e2e/consent.py` exists for
  this: every flow posting to `/consent/admin/shares` sends a complete `legal_basis`, so a
  refusal there is always about the credential.
- **A flow that records no step must not report PASS.** Check what `FlowResult.passed`
  actually evaluates before trusting a green run.
- **A refusal must be attributable to the thing you removed.** Two refusals that look
  identical on the wire — the provider denying, and *our* connector declining to ask (409
  deduplication) — are the difference between an assertion and a placebo. `fail_closed.py`
  classifies every attempt by which side answered and fails on the wrong one; copy that shape
  before writing another negative flow.

## The route table is derived

`api_contract.py` reads every service's `/openapi.json` and sweeps what it finds
(`route_inventory.py`). **Adding a guarded route to a service needs no change here** — it is
probed the moment the app publishes it, because `ds_auth.require_permission` marks it with
the `DataspacePermission` security scheme. The previous hand-kept table covered 70 of 110
routes and nothing said so (`E2E-03`).

What is still declared by hand is the *opposite* — the routes that are **not** expected to
refuse a bearer-less caller:

| Table | Means |
|---|---|
| `ANONYMOUS_ROUTES` | reachable with no credential by design. Adding a line widens the anonymous perimeter |
| `PUBLIC_ROUTES` | the subset asserted to answer **200**, as concrete paths |
| `SELF_AUTHENTICATED_ROUTES` | refuses, but on a VC-JWT or a DCP token rather than a permission — so the wrong-scope battery would prove nothing about it |
| `HIDDEN_ROUTES` | `include_in_schema=False`, so absent from the document the sweep reads |

**A published route in none of them fails the sweep**, which is the fail-safe direction:
forget to classify a new route and it gets probed for refusal. Two things the derivation
cannot see are checked in `tests/test_route_inventory.py`: that the scheme name still agrees
with `ds_auth`'s (this package deliberately does not import it), and that no service hides a
route from its OpenAPI document without declaring it.

The wrong-scope sweep uses `svc-ds-federated-catalog` as the under-privileged client, and
which routes it legitimately holds is now **read from its own token's `scope` claim**
intersected with the permissions each route publishes — the realm answering, rather than a
comment about the realm.

## The unit suite may not touch the network

`tests/conftest.py` refuses every outbound socket, autouse. This is not hygiene:
`run_cleanup` built its own `httpx.Client` rather than taking one, so `task test` —
eight green tests that mocked `psycopg` and `HttpClient` — **deleted every contract
definition and policy from the running dev stack's three EDCs** (`E2E-17`). The
assets survived, because their deletes 409 while an agreement references them, so
the damage looked like a half-finished provider sync and cost three sessions.

**If a test trips the guard, inject the client — do not add an exemption.** A code
path that constructs its own HTTP client or database connection is one no caller can
isolate, and that is the defect the guard is reporting.

## Scenario fixtures

The `chain-*` flows assert against declared fixtures rather than creating their own. Flows
that provision inline pass on a dirty stack, fail on a clean one, and leave residue that makes
the *next* run pass for the wrong reason.

```bash
ds-e2e scenario apply | show | destroy
```

Everything is provisioned through the identity-registry **admin API**, never the database, so
one file works against a local stack, compose or a cluster. Three properties any new scenario
must keep:

- **Idempotent and convergent.** A second `apply` is a no-op *and* repairs what the previous
  `destroy` left. Deregistering deactivates rather than deletes (a DID that transacted stays
  auditable), so `apply` reactivates instead of reading the 409 as "done".
- **Narrow destroy.** Only the aliases and DIDs the scenario names.
- **Preconditions stop the run.** Agreements come from files via `ir-cli agreement import`
  and offers are served from YAML; the scenario *asserts* both and names the command to fix.
  Provisioning owners on top of a wrong-capacity agreement makes the circle assertions pass
  for the wrong reason.

The consent vocabulary the flows assert against is pinned in `config.py` and must stay in
step with `sharing-offers.yaml` and the ODRL profile. **The negative purpose is deliberately
one the dataset permits but the subject never agreed to** — that is the case proving the
purpose chain is enforced rather than merely declared.

## Adding a flow

1. `flows/my_flow.py` — a `BaseFlow` subclass implementing `execute() -> FlowResult`
2. Register in `flows/__init__.py` (and `FAST_FLOWS` if it needs no EDC)
3. Add to `FlowName` in `cli.py` — a test asserts enum and registry match
4. Add `task e2e:<name>` to the root `Taskfile.yml`
5. Declare fixtures in a scenario rather than creating them in `execute()`, and revoke
   anything the flow itself writes
6. Override `cleanup()` if the flow changes anything outside its own records — `run_flow`
   calls it in a `finally` for every flow, including the exception and Ctrl-C paths

## A flow that stops a service

`fail-closed` is the only one, and its three traps generalise. Read
`flows/fail_closed.py`'s header before changing it; the short version:

- **Target an offer the PDP actually decides.** Only `{ns}Membership` and `{ns}ConsentStatus`
  reach ds-connector. `odrl:purpose` is evaluated inside the EDC JVM, so a flow targeting a
  purpose-only offer stops a service that the negotiation never consults — and reports a
  fail-open. `_assert_offer_needs_the_pdp` checks the *published* offer, not `governance.yaml`.
- **Outlast `ds.access.scope.cache.ttl.seconds`** (default 60, and now actually passed to the
  EDC containers). It is the window in which the platform cannot fail closed, and it bounds
  recovery too — the `false` computed during an outage outlives the restart.
- **Restore in `cleanup()`, not only on the happy path.** Everything after a flow that leaves
  a container down fails for reasons of its own.

Sync httpx — no async needed for a sequential runner. Known gaps are in
`.agents/defect-per-service.md`.
