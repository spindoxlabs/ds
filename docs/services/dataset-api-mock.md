# dataset-api-mock

A stand-in for the participant-operated **dataset API** — the service that actually holds the
data — so the platform can be run and tested without one.

It serves a small fixed set of sample datasets over a catalogue surface and a `POST /query`
surface, and on that query surface it acts as the **data-plane policy enforcement point**: it
verifies the EDR bearer token, asks [`ds-connector`](connector.md) whether rows may flow,
applies the row filter it gets back, emits a query-audit event, and only then returns rows.

!!! note "It is a fixture, not a component"
    Nothing deploys this. The real dataset API is participant-operated and external; the Helm
    charts carry its URL and nothing else. Exclude it from assessments of the platform.

    But **keep it aligned.** It mirrors the real signature deliberately, and it is the
    reference implementation of the PEP contract. A flow that passes only against the mock is
    evidence about an API nobody runs — so when the connector's `/internal/*` contract
    changes, this changes with it, in the same commit.

## Role in the blueprint

| | |
|---|---|
| Stands in for | [DSSC · Data Exchange](../blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Control and Data Plane](../blueprints/dssc/control-and-data-plane.md) |
| Rules it demonstrates | [Rulebook · Data exchange](../rulebook/data-exchange.md) — the plane split, and what may not start before the control plane has decided |

## The contract it mirrors

`POST /query` with `{sql, limit, offset, skip_count}`, answering
`{items, offset, limit, count, total}`.

**The datasets come from the SQL**, not from a parameter. That is the real service's contract:
the caller sends a statement, and the API works out which datasets it touches. An earlier
shape took `dataset_name`, `consumer_id`, `subject_id`, `agreement_id`, `transfer_id` and
`purpose` as parameters — a contract production has never implemented.

Dataspace context arrives in headers:

| Header | Carries |
|---|---|
| `Authorization` | the EDR bearer token; its `aud` is the consumer's DID |
| `Edc-Contract-Agreement-Id` | the agreement; **its presence is what selects dataspace mode** |
| `Edc-Transfer-Process-Id` | the running transfer |
| `Edc-Purpose` | comma-separated declared purposes |

The rest of the surface is a catalogue: `GET /catalogue`, `GET /catalogue/{asset_id}`,
`GET /datasets`, and `GET /subjects/{subject_id}/datasets` — which tells a person which
datasets contain rows about them, without granting any access to them.

## How it works

### Two modes, chosen by one header

```
POST /query without Edc-Contract-Agreement-Id   →  plain: open datasets only, no token, no decision
POST /query with    Edc-Contract-Agreement-Id   →  dataspace: the full enforcement chain
```

Dataspace mode never falls back to the plain path. A failure at any step is a refusal, not a
downgrade.

**The plain path cannot reach a consent-gated dataset.** It used to: omitting one header
returned every row of a `requires_consent: true` dataset with no token, no decision and no
audit event, and the header is the caller's to send — so the gate was opt-in for the party it
exists to constrain. Datasets with no data subject behind them still flow that way, which is
what the path is for.

**One statement names one dataset.** A statement touching several is refused. ds authorises
every dataset the statement names, and this plane used to serve the first of them — silently,
with the audit event naming only the one served.

**A dataset name is matched as a reference, not as a substring.** Comments and single-quoted
literals are removed first, and the name must then appear undelimited by identifier characters
or dots. `-- see datasets.silver.meters_15m` used to select it, and that string decides which
asset id is sent to `authorize` — so it decides which agreement and which consent pool answer.

### The enforcement chain

1. **Resolve the datasets** named in the SQL.
2. **Verify the EDR token.** The mock fetches the provider's signing keys from
   `GET /internal/edr-jwks` on the connector and tries the token against each of them. It
   deliberately does not index by `kid`, because the EDC sets `kid` to its vault alias rather
   than to the JWK's own. The first `aud` becomes the consumer DID.
3. **Ask the connector** at `POST /internal/dataplane/authorize` with the consumer DID,
   agreement, transfer, purposes and dataset ids.
4. **Act on the answer.** Parsed as `ds.governance.DataplaneDecision` — the shared shape, so
   an unrecognised key is a parse failure rather than a silently dropped narrowing. `allow`
   on both the envelope *and* this dataset's verdict continues; anything else — including a
   dataset the decision never mentions — is a `403` relaying the reason. A non-2xx from the
   connector is a `502`; so is a connector that cannot be reached, and so is a body that will
   not parse. **ds unreachable is a denial, never an allow, and neither is ds unreadable.**
5. **Apply the row filter** from the per-dataset verdict, dispatching on its `handler`. This
   service implements `direct_user_match` and `rec_registry`; a handler it does not implement
   withholds every row, because an *allow* carrying a filter says *these rows*, not *all
   rows*.
6. **Audit** the query back to the connector, which forwards it as a `QueryExecuted`
   provenance event. **Any failure here refuses the query** — see below.
7. **Page and return.**

Both the JWKS fetch and the authorize call carry a Keycloak service token as
`svc-ds-dataset-api`, which holds `connector.internal` — by name, so a platform admin token
does not open the internal API. So does the outbound call to an external dataset API, which
used to go out with no credential at all.

### Everything that will not answer is a denial

`_authorize` was always fail-closed. The paths around it were not, and they failed in three
different ways: the JWKS fetch let `raise_for_status` escape as a **500**, the Keycloak token
fetch did the same, and the audit call *ignored* a non-2xx, swallowed a connection error, and
raised a 500 out of the token fetch — three outcomes for one event, two of which served the
rows anyway.

They are now uniform: a dependency that will not answer is a `502`, and no rows leave.

**The audit event is not optional** (rulebook `L-1`). That is affordable here because of where
the call sits — the rows are read and narrowed but not yet returned, so a request that fails
at the audit step discloses nothing and therefore needs no record. This deliberately differs
from the connector's provenance emission, which is non-fatal and retried (`L-4`): that code
records things that have already happened and cannot un-happen them, so retrying is its only
option. This one can still refuse.

### The row filter's handlers

The filter arrives whole — `{handler, args, principals}` — because the handler is what knows
how a person maps to values in the column. ds names the person by an identifier **native to
the receiving system**, never by DID.

| Handler | Resolves |
|---|---|
| `direct_user_match` | nothing — the column holds the principal itself |
| `rec_registry` | a member to the meters they own, through the REC registry |

**Handler names belong to the data plane, not to `ds.governance`.** ds passes the handler
through from `governance.yaml` and never interprets it — `DataplaneRowFilter` says as much
where it declares `args` open: *"a handler defines its own arguments and the PDP does not
interpret them"*. Which registry resolves a principal to column values is a property of the
system holding the data, so a control-plane library enumerating handlers would invite ds to
reason about one it cannot run. `rec_registry` is therefore named in this service.

The two ends still have to agree, and they agree through **`governance.yaml`** — the
producer's declaration, which the connector reads and this plane must recognise. That is what
the fixture test checks against, which is stronger than a shared constant because it is the
file the connector actually reads.

`direct_user_match` is the exception, and imported from `ds.governance` for a reason that does
not generalise: `celine-utils/schema/governance.schema.json` names it, and it is what the
legacy `user_filter_column` spelling migrates to on both sides — so it is part of the shape
rather than a handler choice.

## Configuration

`pydantic-settings`, prefix `DATASET_API_`, instantiated at import — a bad value fails the
import, not a request.

| Variable | Default | Meaning |
|---|---|---|
| `DATASET_API_CONNECTOR_INTERNAL_URL` | `http://172.17.0.1:30001` | the connector's `/internal/*` base |
| `DATASET_API_KEYCLOAK_TOKEN_URL` | Keycloak on `172.17.0.1:9080` | token endpoint |
| `DATASET_API_SERVICE_CLIENT_ID` / `_SECRET` | `svc-ds-dataset-api` | **secret** — its own client |
| `DATASET_API_VERIFY_EDR` | `true` | verify the EDR token against the connector's JWKS. Off ⇒ any bearer string names any consumer. **Refused in production** |
| `DATASET_API_EXTERNAL_QUERY_URL` | — | proxy datasets marked `source: external` to a real dataset API |
| `DATASET_API_EXTRA_DATASETS_PATH` | — | JSON file merged into the built-in fixtures at import |

There is deliberately no `DATASET_API_ENFORCE_CONSENT`. One was declared, defaulted to `true`,
set in `docker-compose.rec.yml` and listed in `.env.example` — and read by nothing. Three
places described this PEP's consent enforcement as a switch that did not exist, which an
operator could have turned "on" during an incident to no effect and no warning. Consent
enforcement is not configurable here: the decision is ds's, and this service either applies it
or refuses.

Port **30002**, hardcoded. When the real dataset API is running it takes 30002 and
`DATASET_API_MOCK_PORT=30022` moves the mock — which is what the committed dev
configuration does.

## The fixtures

Two built-in datasets, chosen to cover both sides of the consent decision:

| Dataset | Consent | Shape |
|---|---|---|
| `datasets.gold.om_weather_features` | not required | open weather features |
| `datasets.silver.meters_15m` | **required** | metering rows keyed by `device_id`, narrowed by a `rec_registry` filter |

**The gated dataset is declared exactly as `governance.yaml` declares it.** It used to key rows
by subject DID in a column `sub`, while governance declared a `rec_registry` filter on
`device_id` and ds sent Keycloak usernames — three vocabularies with no overlap, and nothing
that could notice. An *allow* narrowed to nothing, which is indistinguishable from a subject
who consented to nothing, so the platform's one consent-gated dataset was unserveable against
the mock and no test said so. A test now reads both files and fails when they drift.

A DID no longer appears in any payload column, which is also what rulebook `L-3` requires of
anything that travels with the rows: a DID here is derived from an unsalted email hash, so it
re-identifies the subject to whoever later holds them.

Resolving a member to their meters needs two registries the real data plane has behind it and
a stand-in does not, so `REC_MEMBERS` collapses both hops into one fixture — the
identity-registry's DID↔username bridge and the REC registry's member↔device map. Its members
and sensor ids are `fixtures/ds_e2e_rec.yaml`'s, so a query answers the same whichever backend
holds `:30002`.

`fixtures/` is not read by the mock at all — it seeds the **real** dataset-api and REC
registry stack for end-to-end runs. `fixtures/seed.sh` brings that stack up, creates a
physical table, imports a catalogue entry and a community fixture, and deliberately includes
one meter that belongs to nobody as a negative control for the row filter. The mock's own
fixture carries the same unowned meter, for the same reason.

An extra dataset supplied through `DATASET_API_EXTRA_DATASETS_PATH` must declare
`requires_consent`, an `asset_id`, and either `rows` or an external query — and a row filter
if it is consent-gated. None of these is defaulted. An absent `requires_consent` read as
`False` would publish a PII dataset as open, and `requires_consent` and `rows` used to be read
with `spec["…"]`, so omitting either was a `KeyError` out of the unauthenticated `/catalogue`.

## Running it

| Task | Effect |
|---|---|
| `task provider:dataset-api:run` | uvicorn on `:30002` with reload |
| `task -d services/dataset-api-mock debug` | debugpy on `:30902` |
| `./services/dataset-api-mock/fixtures/seed.sh` | bring up and seed the **real** dataset-api stack instead |
| `task -d services/dataset-api-mock test` | the unit suite |
| `task -d services/dataset-api-mock lint` | ruff over `src/` and `tests/` |

The unit suite's core is **what this PEP does with a decision** — the half of the
`/internal/*` contract the connector's own tests cannot reach. It exists because the two ends
of that contract disagreed about the row filter's shape with no test on either side. Around it
sit three checks for failures that are invisible by construction: what the request *is* before
any decision is taken, what happens when a dependency will not answer, and whether this
service's vocabulary still matches `governance.yaml`'s.

The rest is the `ds-e2e` smoke flow, which asserts the outcomes that matter against a live
stack: a consented query returns rows, an unconsented purpose is refused, a query with no
purpose is refused, and a foreign agreement id is refused.
