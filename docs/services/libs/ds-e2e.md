# ds-e2e

The `ds-e2e` CLI: **sixteen named flows** that drive a running platform over HTTP and report
pass or fail per assertion.

It is not a test runner for the other units — those have their own unit tests. This is the
harness that exercises the *system*: real tokens, real DSP exchanges between two EDCs, real
consent decisions, real row filtering. **It is the only harness that exercises the real DSP
exchange**, so its blind spots are the platform's.

Alongside the flows it ships a declarative fixture provisioner, a destructive state reset and a
reachability probe.

Nothing in the platform imports it; it is invoked from the root `Taskfile.yml`.

## Role in the blueprint

| | |
|---|---|
| Verifies | all of them — start from [the blueprint index](../../blueprints/index.md) |
| Rules | [the rulebook](../../rulebook/index.md) — a flow should assert a rulebook rule, and the rule should name the flow |

## Commands

```sh
ds-e2e run --flow smoke [--clean-first] [--format text|json|markdown]
ds-e2e clean
ds-e2e health
ds-e2e scenario apply|show|destroy [--scenario energy-chains]
```

`run` exits non-zero if any selected flow fails. `health` probes `/health` on the connector
pair, the dataset API, both provenance instances and the identity registry.

## The flows

| Flow | Exercises |
|---|---|
| `smoke` | the whole consumer-pull exchange: sync → catalogue → negotiate → transfer → EDR → query, plus consent and revocation |
| `api-contract` | the public/guarded perimeter of every service: which routes need a token, which need which scope, input validation, method discipline |
| `authz-perimeter` | that a subject's routes refuse a service token, and vice versa |
| `user-authority` | that a participant admin scoped to one organisation cannot write another's assets |
| `dcp-trust` | DID resolution, STS token minting, presentation queries, the status list |
| `consent-purpose` | that a purpose outside the consented set is refused, and a narrower one inside it is allowed |
| `consent-request` | the full consent lifecycle: request → pending → reject → re-request → approve → revoke, with provenance |
| `org-onboarding` | the five onboarding gates end to end, up to a resolvable participant DID |
| `chain-community` / `chain-partner` / `chain-unbundling` | the disclosure chains — who may receive data as a processor, a partner, or an independent controller |
| `uc1` / `uc2` / `uc3` | the three business use cases |
| `semantic-model` | the payload model a producer publishes is the one every data plane states and serves a vocabulary for — read-only, and it names which backend answered |
| `catalog-discovery` | catalogue freshness, shape, resolution, search and paging |
| `lineage` | ingestion → provenance events → lineage traversal → audit log |
| `two-providers` | that a second provider with no members keeps its own catalogue, governance and counterparty |
| `fail-closed` | **stops `ds-connector` and proves the negotiation gate denies**, then that service resumes. Runs last, takes ~3 minutes — it must outlast the EDC's decision cache in both directions — and needs the Docker topology |

Four aggregates: `all`, `fast`, `security` (`api-contract`, `authz-perimeter`,
`user-authority`, `dcp-trust`) and `chains`.

| Task | Runs |
|---|---|
| `task e2e` | `smoke` |
| `task e2e:all` | everything, after `e2e:prepare` |
| `task e2e:fast` / `e2e:security` / `e2e:chains` | the aggregates |
| `task e2e:<flow>` | most individual flows |
| `task e2e:prepare` | clean → restart the EDCs → wait for readiness → apply the scenario |
| `task e2e:clean` / `e2e:health` / `e2e:scenario:apply` | the supporting commands |

## How a flow works

Each flow is a class that makes a sequence of live calls and records a `Step` per assertion.
Every step **short-circuits**: the flow returns its partial result on the first failure rather
than continuing, so a report always names the first thing that broke.

Taking `consent-request` as the shape of it:

1. health-check the connector;
2. get a service token;
3. resolve the data subject through the identity registry and take their credential;
4. as the *service*, request consent from that subject;
5. verify the consent check reports **not** active — a pending ask is not a grant;
6. as the *subject*, see the request in their own pending list, and see no foreign rows;
7. reject it; verify the check stays closed; verify a replayed approval is refused;
8. request again, approve, verify the check now opens;
9. verify the check stays closed for an unconsented purpose;
10. revoke, verify the check closes and the record keeps its revocation timestamp;
11. verify both a `ConsentGranted` and a `ConsentRevoked` event reached provenance.

That is the pattern: assert the positive, then assert the negative, then assert the record.

## Four ways it authenticates

| Path | Grant | As |
|---|---|---|
| service token | `client_credentials`, cached | `svc-ds-e2e` |
| a second service token | `client_credentials`, uncached | any client — used for an admin client and a low-privilege one, to probe the boundary |
| user token | `password` grant | a dev-realm user, through the browser login client |
| subject credential | `X-Subject-Id` + `X-User-VC`, fetched from the identity registry | the dev subject and consumer users |

The password grant works only because the dev realm enables direct access grants on the login
client — a production realm does not, and that path does not exist there.

## Scenarios

`ds-e2e scenario apply` provisions fixtures declaratively from a YAML file, through the
identity registry's admin API: owners, agreement acceptances, memberships and participants. It
is idempotent — a `409` everywhere is success — and it aborts *before any write* if a required
agreement version is missing, reporting the exact remediation command.

`destroy` touches only aliases and DIDs the scenario names, and removes participants before
owners.

The shipped scenario, `energy-chains`, sets up the community, partner, outsider and grid-operator
organisations the three chain flows need.

## `clean` is destructive

`ds-e2e clean` truncates the connector and provenance application tables in both participants'
databases, **drops and recreates** both EDC databases, clears the EDC management stores, and
then re-syncs the provider's governance.

It is the reset used before a full run. It is not a thing to point at anything you care about.

## Configuration

`pydantic-settings` with **no prefix**. Roughly fifty fields; a field with an explicit alias
deliberately reuses another unit's variable name, so one `.env.local` configures both.

| Group | Variables |
|---|---|
| Service URLs | `CONNECTOR_URL`, `CATALOG_CONNECTOR_URL`, `CONNECTOR_DATASET_API_URL`, `CONNECTOR_PROVENANCE_URL_PROVIDER` / `_CONSUMER`, `CONNECTOR_IDENTITY_REGISTRY_URL`, `FEDERATED_CATALOG_URL` |
| DSP | `E2E_COUNTER_PARTY_ADDRESS`, `CONNECTOR_PARTICIPANT_DID`, `CONNECTOR_CONSUMER_PARTICIPANT_DID` |
| Clients | `KEYCLOAK_TOKEN_URL`, `SVC_DS_E2E_ID` / `_SECRET`, `SVC_DS_IDENTITY_REGISTRY_*`, `SVC_DS_FEDERATED_CATALOG_*`, `OAUTH2_PROXY_CLIENT_ID` / `_SECRET` |
| Dev users | `ADMIN_*`, `PROVIDER_*`, `GRID_OPERATOR_*`, `CONSUMER_*`, `DATA_SUBJECT_*`, `OWNING_ORG`, `OTHER_ORG` |
| Fixtures | `ASSET_ID`, `SHARING_OFFER_ID`, `CONSENTED_PURPOSE`, `UNCONSENTED_PURPOSE`, `ORG_*` |
| Timing | `POLL_TIMEOUT` (120), `POLL_INTERVAL` (2.0), `REQUEST_TIMEOUT` (30) |
| Cleanup | `SMOKE_DATABASE_URL` — the DSN stem; each database name is appended |

Values reach the harness through the root `Taskfile.yml`'s `dotenv` directive, which exports
`.env` and `.env.local` into the task environment before the CLI starts.

## What it needs running

Everything. Specifically: PostgreSQL with the four application databases and both EDC
databases; Keycloak with the realm, the service clients, the login client and the dev users;
the identity registry bootstrapped with the trust anchor, participants and credentials; both
connectors; both provenance instances; the dataset API; the federated catalogue; both EDCs;
the service agreements seeded; and, for the chain flows, the scenario applied.

`task e2e:prepare` is the packaged path to all of that.
