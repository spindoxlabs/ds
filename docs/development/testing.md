# Testing

Five layers. Each proves something the others cannot, and the reason to name them is that a
result from one is routinely mistaken for a result from another.

| Layer | Command | Proves |
|---|---|---|
| **Unit** | `task -d <unit> test` | logic, in isolation. Mandatory for every change |
| **Integration** | `task -d <unit> test:integration` | the unit against its real dependencies — database, Keycloak, the connector's `/internal/*` — without the rest of the dataspace |
| **Local stack** | `task dev:restart` | the code works against real dependencies, with hot reload |
| **Docker e2e** | `task docker:restart` then `task e2e:all` | the images, compose env and startup order work |
| **Portal UI** | `task -d services/portal test:ui` | Playwright journeys against the running stack |

## The rule these layers exist for

**A green run is only evidence about the thing that actually ran.** Three failures in this
repository were all of that shape, and none of them was a wrong answer — each was a check that
never executed:

- the data-plane row filter matched no key the connector sends, so an *allow* narrowed to
  nothing and looked exactly like a subject who had consented to nothing;
- the negotiation-scope consent function read an attribute nothing sets, so it returned
  "permitted" for every negotiation ever run;
- `:edc-extensions:test` existed and was invoked by no task, so the constraint functions that
  decide every access were untested by any workflow.

Each passed every suite throughout. So when a layer reports success, ask what it exercised —
and if that is not visible from the output, **make it visible**, in the product rather than in
the test. `NegotiationConsentValidator` logs on the *allow* path for exactly this reason: an
enforcement point that is silent when it permits cannot be distinguished from one that never
ran.

## The data plane has two implementations, and e2e must cover both

The dataspace addresses its data plane as an HTTP endpoint on `:30002`, and **two different
services can be behind it**:

| Behind `:30002` | What it is |
|---|---|
| celine `dataset-api` | the real, participant-operated data plane. What a deployment runs |
| `services/dataset-api-mock` | a stand-in, and the **reference implementation** of the PEP contract |

`services/dataset-api-mock/fixtures/seed.sh` puts the real one on `:30002` and moves the mock to `:30022`
(`DATASET_API_MOCK_PORT`, a committed default). `ds-e2e` reads
`CONNECTOR_DATASET_API_URL`, default `http://172.17.0.1:30002`.

So **an ordinary `task e2e:all` exercises the real dataset-api and never the mock.** That is
the right default — a flow that passes only against the mock is evidence about an API nobody
runs. But it leaves two hazards, and both are live:

1. **The mock can drift and nothing notices.** It is the reference PEP other implementations
   are written against, and no end-to-end flow touches it. Its row-filter shape disagreed with
   the connector's for as long as it did because neither end had a test.
2. **The same command means different things depending on stack state.** Whichever service
   holds `:30002` answers, and *nothing in the run output records which one did*. A suite that
   cannot tell you what it tested cannot be cited as evidence that the two agree.

**Both backends must be run, and each run must name the backend it used.** Until that is
wired, a change to either data plane needs its own check — see
[`docs/services/dataset-api-mock.md`](../services/dataset-api-mock.md).

## Integration tests: the gap between unit and e2e

Unit tests stub the dependency; e2e needs the whole dataspace standing. Between them sits
everything that is real but not global — a migration against a real Postgres, a token against
a real Keycloak, a `/internal/*` call against a real connector — and today most of it is
verified by neither.

That gap is where the failures above lived. The row-filter shape was a **contract** between two
services: each end's unit tests passed against its own reading of it, and e2e never touched
the mock, so nothing compared them.

### What exists today

| Unit | `test:integration` | Covers | Runs in CI |
|---|---|---|---|
| `services/connector` | yes | the 8 migrations against a real Postgres, and the migrated schema vs the models | `integration.yml` |
| `services/provenance` | yes | the same, for its 3 migrations | `integration.yml` |
| `services/identity-registry` | yes | a DCP round trip across a trust anchor and two participants | `integration.yml` |
| `libs/ds-auth` | yes | `ds_auth` against a **real Keycloak realm** | `integration.yml`, which provisions the realm itself |

The first two exist because of a gap worth naming: **every Python service builds its unit-test
schema with `Base.metadata.create_all` on SQLite in memory.** So the migrations run in no unit
test, and no model is ever exercised against PostgreSQL. A model changed without a revision
keeps all 319 connector tests green and is found by a deployment. `services/connector/src/connector/db/engine.py`'s startup guard
does not catch it — it compares the recorded revision *stamp* against head, so a database that
is at head and shaped wrong passes.

Both suites create and drop their **own** database and never touch the developer's. Both were
verified by mutation, not by observing them pass: adding a column to a model with no revision
turns each red.

They also found four columns per service where the migrations left a timestamp nullable and the
model declares it `NOT NULL`. Recorded as a **ratchet** (`KNOWN_NULLABLE_DRIFT`) rather than
fixed, because the remedy is an `ALTER COLUMN … SET NOT NULL` against every deployed database —
a schema change with its own blast radius, and not something a test should smuggle in. A ninth
one fails.

`services/identity-registry`'s suite **had been red since `D-51`** and is the reason this
workflow matters. It drove `ir-cli participant add`, which that change deliberately removed when
participant enrolment became a two-party handshake — and because no workflow invoked the suite,
nothing said so. The `EDC-09` / `REV-01` pattern applied to an integration suite.

It now follows the real handshake, and that made it a stronger test rather than merely a green
one. Three processes instead of two:

```
anchor:       ir-cli bootstrap → owner add → org enrolment-token --alias <owner>
participant:  ir-cli participant init --code <code>     # generates its own key
```

The participant generates its keypair locally and sends the anchor a *signature*; the anchor
resolves its DID document over real did:web to get the public half. Two things follow that the
old two-peer harness could not assert. **A participant must be serving before it can enrol** —
the anchor fetches `did.json` over HTTP and there is no local shortcut, which is the same order
`docker-compose.rec.yml` encodes by making `ir-rec-bootstrap` wait for `ir-rec` to be healthy.
And **the trust anchor is genuinely a third party**: `the credential is signed by the trust
anchor` used to compare two DIDs served by one process, and now names a key held in a database
the holder cannot read.

Verified by mutation: drop the `--code` and five tests fail, including every custody assertion.

`libs/ds-auth`'s suite closes the second thing this page asks for — *authentication against a
real Keycloak, not a stubbed verifier*. Two suites existed and neither could see the gap:
`test_verify.py` **signs its own tokens**, so the RS256 / published-`kid` / list-valued-`aud`
shape a real realm produces had never met `verify_token`; and `test_vocabulary.py` compares
`clients.yaml` with `ds_auth.bundles` — declaration against declaration. What *applies* them is
`celine-policies keycloak sync`, and its result was checked by nothing. That is `KC-01`'s shape:
a realm synced before a value was set keeps the old one, silently, until a 403 at runtime.

It asserts `default_scopes` ⊆ the token's `scope` claim, per client, for all eight — a subset
because a deployment's domain overlay legitimately adds more. Verified by mutation: declare a
scope the realm does not grant and it fails, naming the scope and the remedy.

**CI runs the real provisioning tool.** `realm-dataspaces-dev.json` carries only `oauth2_proxy`
and six stock scopes, so a bare Keycloak proves nothing — but the `celine-policies` image is
public and every input it needs (`clients.dataspaces.yaml`, `clients.yaml`, each overlay, the realm file) is committed, so the
`keycloak` job in `integration.yml` starts Keycloak and syncs it exactly as `docker-compose.yml`
does, then asserts against the result. That is the point: what is under test is **the sync's
output**, so a job that skipped the sync would be testing nothing. Measured both ways —
provisioned realm: 13 passed; same realm without the sync step: 8 failed, 5 errors.

The suite **skips on a laptop with no stack and fails when `CI` is set**. `CI-02`'s rule applied
one layer out: an absent dependency has two meanings. *No stack is running* is a supported mode
for a developer; in CI the job provisions the realm itself, so its absence is a broken workflow,
and skipping would report green for a suite that asserted nothing.

### What does *not* need a layer

"One per service" would be cargo cult, and three of the four categories above are already
answered or belong elsewhere:

| Unit | Verdict |
|---|---|
| `services/federated-catalog` | **no database, no migrations.** Its real dependencies are the EDC catalogues and the identity registry, which is what `ds-e2e`'s `catalog-discovery` flow already exercises live |
| `services/portal` | has one, under a different name: `test:ui` is Playwright against the running stack |
| `services/dataset-api-mock` | a stand-in, excluded from assessments. The contract it must honour is `T-3`'s, not this row's |
| `services/edc-connector` | a Gradle fat-JAR build with no source of its own |
| `services/edc-extensions` | its `:test` runs in `tests.yml`; a real EDC exercise is `ds-e2e`'s job |
| `libs/ds-edc` | its dependency is a running EDC — an e2e concern, and `ds-e2e` drives every method that matters |
| `libs/governance` | pure library. Its one real-dependency test is `test_dataplane_contract.py`, which is `T-3` |
| `libs/ds-obs` | logging and metrics configuration; nothing to integrate against |
| `libs/ds-e2e` | **is** the stack layer |

So `T-2` is done: four units, all four in CI. What remains is `T-1` — running the *flows*
against both data planes — which is a different row and does not block anything here.

### What still belongs here

**Each service should carry an integration layer** under `task -d <unit> test:integration`,
kept separate from `test` so the unit suite stays fast and dependency-free. What belongs there:

- the service against a real database, including migrations
- authentication against a real Keycloak, not a stubbed verifier
- **contract tests shared by both sides of an internal API** — the same cases run against the
  connector's real response and against every PEP that consumes it. A shared shape in
  `libs/governance` (`ds.governance.dataplane`) makes the *type* common; it does not make the
  *behaviour* common
- startup invariants: a setting nothing reads, a bound operand with no function, a route with
  no guard

## Consistency between the layers

The three layers must agree about the same behaviour, and where they can disagree, something
should fail:

- **A fixture must match the declaration it claims to implement.** `services/dataset-api-mock`
  now reads `governance.yaml` and the REC fixture in its own suite and fails on drift, because
  a mismatch here narrows silently rather than raising.
- **A vocabulary belongs in one place.** Handler names, scopes and event types spelled
  independently at each end agree until somebody renames one side.
- **Prefer a test that can fail because of something a change did *not* do.**
  `test_settings_are_read.py` is the pattern: it sweeps every setting and fails on one nothing
  reads, in both directions — a declared-and-unread field, and a deployment file naming a
  variable no field backs.

## Reading the database directly

One Postgres on `35432`, one database per service, `postgres`/`postgres` in dev:

```bash
psql -h 172.17.0.1 -p 35432 -U postgres -l                    # list service databases
psql -h 172.17.0.1 -p 35432 -U postgres -d connector -c '…'   # inspect state precisely
```

An assertion about consent, agreement or provenance state is worth more when it is checked
against the row than against an API response.
