# ds-e2e

The `ds-e2e` CLI. Sixteen named **flows**, each a class making a sequence of live HTTP calls
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

## The two route tables

`api_contract.py` holds `PUBLIC_ROUTES` (must answer anonymously) and `_guarded_routes()`
(must refuse). **Adding a route to a service means adding a line to one of them.** Unit tests
assert the tables are disjoint and duplicate-free, but nothing can detect a route in neither —
that is a review responsibility.

The wrong-scope sweep uses `svc-ds-federated-catalog` as the under-privileged client; its
`held` set must stay in step with `services/keycloak/clients.yaml`. **Verify that against the
realm rather than a comment** — it is currently wrong, and the effect is that three routes
are excluded from the sweep that exists to test them.

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

Sync httpx — no async needed for a sequential runner. Known gaps are in
`.agents/defect-per-service.md`.
