# ds-e2e — Agent Guide

End-to-end verification framework for the dataspaces platform.

## Source layout

```
src/ds_e2e/
├── cli.py          Typer CLI (run, clean, health)
├── config.py       E2ESettings — pydantic-settings, reads .env.local
├── http.py         HttpClient — sync httpx, polling, service token caching
├── models.py       Step, FlowResult
├── runner.py       Flow orchestration (run_flow, run_all, run_selected)
├── cleanup.py      DB truncation + EDC state reset + provider sync
├── scenario.py     Declarative fixtures — apply / show / destroy
├── scenarios/
│   └── energy-chains.yaml  Fixtures for the three delegation chains
└── flows/
    ├── __init__.py         Flow registry + FAST_FLOWS / SECURITY_FLOWS subsets
    ├── base.py             BaseFlow ABC
    ├── api_contract.py     API surface contract — refusal, validation, leak checks
    ├── authz_perimeter.py  Cross-subject isolation, role confusion, enumeration
    ├── dcp_trust.py        STS, presentation-query binding, did:web, StatusList
    ├── consent_purpose.py  Consent vocabulary: taxonomy, offers, purpose enforcement
    ├── consent_request.py  Interactive consent: request → approve/reject → revoke
    ├── org_onboarding.py   Organisation onboarding lifecycle and gates (Block D)
    ├── uc1.py              Subject-pool validation (GP-1)
    ├── uc2.py              Owner-scoped negotiation (GP-2)
    ├── uc3.py              Open/external data (GP-3)
    ├── chains.py           The three delegation chains (community/partner/unbundling)
    ├── catalog_discovery.py Federated catalogue crawl, discovery, search, paging
    ├── lineage.py          Provenance graph, event idempotency, audit log
    └── smoke.py            Full DSP consumer-pull flow
```

## Flows

| Flow | Needs the EDC? | Covers |
|---|---|---|
| `api-contract` | no | The public perimeter (pinned), anonymous refusal on every guarded route, wrong-scope refusal, the user-VC negative battery, input validation, method discipline, error-leak checks |
| `authz-perimeter` | no | Header substitution, query-parameter scoping, role confusion, enumeration resistance — with real credentials |
| `dcp-trust` | no | STS refusal paths and token shape, presentation-query DID binding, did:web resolution, StatusList publication |
| `consent-purpose` | no | SKOS taxonomy at `/ns/policy`, the `/ns/sharing-offers` projection, `422` on invalid consent writes, offer expansion, the full `odrl:isA` matrix at `/internal/consent/check` |
| `consent-request` | no | The interactive consent lifecycle: an ask lands pending, subject inbox scoping, rejection finality, approval, purpose bounding, revocation with history retained, provenance. The ask is seeded through the provider-local `POST /consent/request`; in the DSP path `ConsentPendingGuard` writes the same rows from a parked negotiation, so the lifecycle from there on is identical and this flow needs no EDC |
| `org-onboarding` | no | register → verify → agreement → credential → promote, both negative gates, readiness, suspend |
| `uc1` / `uc2` / `uc3` | yes | Governance patterns GP-1 / GP-2 / GP-3 |
| `chain-community` | no | Community-mediated consent: the member's row names the community as controller, the grant is purpose-bounded, and a subject outside the member pool cannot be drawn into it |
| `chain-partner` | no | Capacity is the consent boundary: a processor is disclosed, an independent controller is not covered, and a party that signed nothing gets no capacity at all |
| `chain-unbundling` | no | One legal entity, two controllers: a consent naming the `operations` role does not authorise the `metering` role |
| `catalog-discovery` | yes | Crawl freshness, DCAT-AP shape, dataset resolution, search narrowing, paging |
| `lineage` | partly | Ingestion recording with a consent-snapshot fingerprint, event idempotency, lineage connectivity and depth bounding, audit-log/summary agreement |
| `smoke` | yes | Catalogue → negotiate → transfer → query → revoke, with an offer-based consent grant. Asserts a query for an unconsented purpose **and** a query with no purpose both return zero rows |

Aggregates: `--flow all`, `--flow fast` (everything that runs without the EDC),
`--flow security` (`api-contract`, `authz-perimeter`, `dcp-trust`),
`--flow chains` (the three delegation chains).

`fast` is the set to run on every change; it needs only ds-connector,
identity-registry, provenance, federated-catalog and Keycloak.

## Scenario fixtures

The `chain-*` flows assert against declared fixtures rather than creating their
own. Flows that provision inline pass on a dirty stack, fail on a clean one, and
leave residue that makes the *next* run pass for the wrong reason.

```
ds-e2e scenario apply     # provision, idempotent and convergent
ds-e2e scenario show      # report current state, changes nothing
ds-e2e scenario destroy   # remove exactly what the scenario declares
```

Everything is provisioned through the identity-registry **admin API** — never
the database — so the same file works against a local stack, compose or a
cluster. Three properties the unit tests pin, and which any new scenario must
keep:

- **Idempotent and convergent.** A second `apply` is a no-op *and* repairs
  whatever the previous `destroy` left behind. Deregistering a participant
  deactivates rather than deletes it (a DID that transacted stays auditable), so
  `apply` reactivates instead of treating the 409 as "done".
- **Narrow destroy.** Only the aliases and DIDs the scenario names. Pointed at a
  shared registry it cannot reach an organisation it did not create.
- **Preconditions stop the run.** Agreements are seeded from files by
  `ir-cli agreement import` (their text hashes come from disk), and sharing
  offers are served by the connector from YAML. The scenario *asserts* both and
  reports the exact command or file to fix — provisioning owners on top of a
  missing or wrong-capacity agreement would make the circle assertions pass for
  the wrong reason.

The chain flows also revoke the consent rows they create, so `--flow chains` is
re-runnable in place without `scenario destroy`.

The consent vocabulary the flows assert against is pinned in `config.py`
(`sharing_offer_id`, `consented_purpose`, `unconsented_purpose`) and must stay in step
with `services/connector/governance/sharing-offers.yaml` and the ODRL profile. The
negative purpose is deliberately one the *dataset* permits but the *subject* never
agreed to — that is the case that proves the purpose chain is enforced rather than
merely declared.

## Key design

- **Sync httpx** — no async needed for a sequential CLI runner
- **pydantic-settings** — reads `.env.local` from repo root (same env vars as services)
- **Modular flows** — each flow is a `BaseFlow` subclass registered in `FLOW_REGISTRY`
- **Idempotent cleanup** — truncates connector/provenance tables, terminates EDC negotiations/transfers, deletes EDC objects, re-syncs provider
- **`E2E_COUNTER_PARTY_ADDRESS`** — must match the participant registry's DSP address

### Writing a negative assertion

Use `http.raw(method, url, ...)`, which returns `(status, payload)` and never
raises — `http.get`/`http.post` raise on 4xx, which is the wrong shape when the
4xx *is* the assertion.

Two rules the security flows follow, and new ones should too:

- **A refusal must be a 4xx, not a 5xx.** A guard that raises has let the request
  reach application code before authorisation was settled; the flows treat 5xx as
  a distinct failure class from "allowed", because the fix is different.
- **A skip must be loud.** When a precondition is missing (no STS secret, no
  status list, an empty audit log) the step passes with the reason in its detail
  rather than asserting nothing silently. A security assertion that quietly
  became a no-op is worse than one that was never written.

### The two route tables

`api_contract.py` holds `PUBLIC_ROUTES` (must answer anonymously) and
`_guarded_routes()` (must refuse). **Adding a route to a service means adding a
line to one of them.** The unit tests assert the tables are disjoint and
duplicate-free, but nothing can detect a route that is in neither — that is a
review responsibility.

The wrong-scope sweep uses `svc-ds-federated-catalog` as the under-privileged
client (`low_priv_client_id`); its `held` set in `_check_wrong_scope_refusal`
lists the routes that client legitimately reaches and must be kept in step with
`services/keycloak/clients.yaml`.

## Adding a flow

1. Create `flows/my_flow.py` with a `BaseFlow` subclass implementing `execute() -> FlowResult`
2. Register in `flows/__init__.py` (and add to `FAST_FLOWS` if it needs no EDC)
3. Add to `FlowName` enum in `cli.py` — a test asserts the enum and registry match
4. Add a `task e2e:<name>` entry in the root `Taskfile.yml`
5. If it needs fixtures, declare them in a scenario rather than creating them in
   `execute()`, and revoke anything the flow itself writes

## Known gaps

- Post-revoke query enforcement: **should now be assertable end to end.** The gap
  was that the connector terminated transfers itself (via a `delete_asset`
  placeholder) and the provider EDC's agreement/transfer IDs differ from the
  consumer's, so nothing on the provider side reacted to a revocation.
  `AgreementConsentFunction` is now bound to EDC's `policy.monitor` scope, so a
  revoked consent fails the *provider's* re-evaluation of the agreement policy
  and EDC terminates the transfer through its own state machine. Termination
  takes effect on the next monitor pass rather than synchronously, so an
  assertion needs to poll. The consumer-side workaround in `smoke` should be
  removable — verify against a running stack before deleting it.
- UC1/UC2 membership check: `svc-ds-portal` may lack the scope for the identity-registry `/memberships/check` endpoint
- `dcp-trust` asserts STS *refusals* unconditionally but only asserts issuance when `E2E_PROVIDER_STS_SECRET` is set; without it the positive path is unverified
- No flow asserts EDR token expiry or renewal, nor DSP-level policy enforcement at the provider EDC (only its effect on the consumer's query)
- `uc1`/`uc2`/`uc3` verify preconditions rather than driving their use case end to end; the negative half (a non-member subject actually being refused a delegated consent) is asserted in `api-contract`/`authz-perimeter` instead
