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
POST /query without Edc-Contract-Agreement-Id   →  plain: rows, no token, no decision, no audit
POST /query with    Edc-Contract-Agreement-Id   →  dataspace: the full enforcement chain
```

Dataspace mode never falls back to the plain path. A failure at any step is a refusal, not a
downgrade.

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
   service implements `direct_user_match`; a handler it does not implement withholds every
   row, because an *allow* carrying a filter says *these rows*, not *all rows*.
6. **Audit** the query back to the connector, which forwards it as a `QueryExecuted`
   provenance event.
7. **Page and return.**

Both the JWKS fetch and the authorize call carry a Keycloak service token as
`svc-ds-dataset-api`, which holds `connector.internal` — by name, so a platform admin token
does not open the internal API.

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

Port **30002**, hardcoded. When the real dataset API is running it takes 30002 and
`DATASET_API_MOCK_PORT=30022` moves the mock — which is what the committed dev
configuration does.

## The fixtures

Two built-in datasets, chosen to cover both sides of the consent decision:

| Dataset | Consent | Shape |
|---|---|---|
| `datasets.gold.om_weather_features` | not required | open weather features |
| `datasets.silver.meters_15m` | **required** | metering rows keyed by data subject |

`fixtures/` is not read by the mock at all — it seeds the **real** dataset-api and REC
registry stack for end-to-end runs. `fixtures/seed.sh` brings that stack up, creates a
physical table, imports a catalogue entry and a community fixture, and deliberately includes
one meter that belongs to nobody as a negative control for the row filter.

## Running it

| Task | Effect |
|---|---|
| `task provider:dataset-api:run` | uvicorn on `:30002` with reload |
| `task -d services/dataset-api-mock debug` | debugpy on `:30902` |
| `./services/dataset-api-mock/fixtures/seed.sh` | bring up and seed the **real** dataset-api stack instead |
| `task -d services/dataset-api-mock test` | the unit suite |

The unit suite covers one thing: **what this PEP does with a decision** — the half of the
`/internal/*` contract the connector's own tests cannot reach. It exists because the two ends
of that contract disagreed about the row filter's shape with no test on either side.

The rest is the `ds-e2e` smoke flow, which asserts the outcomes that matter against a live
stack: a consented query returns rows, an unconsented purpose is refused, a query with no
purpose is refused, and a foreign agreement id is refused.
