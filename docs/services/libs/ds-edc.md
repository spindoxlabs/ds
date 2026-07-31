# ds-edc

`import ds_edc`

A typed async client for the **EDC Management API v3**, plus the Pydantic models for its
request and response shapes.

It owns the JSON-LD the platform sends to an EDC control plane — the `@context`, the `@type`,
the camelCase field names and the DSP protocol identifier — and the polling loops that turn
EDC's asynchronous negotiation and transfer state machines into a single awaited result.

It holds no state, reads no configuration, and is constructed per control plane with a base URL
and an API key its caller supplies. [`services/connector`](../connector.md) is its only real
consumer.

!!! note "Not to be confused with `helm/charts/ds-edc`"
    That chart deploys the [EDC connector runtime](../edc-connector.md). This is a Python
    library that talks to one.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Data Exchange](../../blueprints/dssc/data-interoperability/data-exchange.md) |
| Rules it enforces | [Rulebook · Data exchange](../../rulebook/data-exchange.md) — the protocol version pin |

## The protocol pin lives here

```python
DATASPACE_PROTOCOL = "dataspace-protocol-http:2025-1"
```

That string occurs **once in the repository**, and it is sent on every catalogue, negotiation
and transfer request. Changing it is a dataspace-wide breaking change: every counterparty must
speak the same version.

## What it covers

`EdcManagementClient(base_url, api_key)` builds one `httpx.AsyncClient` with a 30-second
timeout and, when a key is given, an `X-Api-Key` header. **The credential is the same for every
method** — there is no per-method credential and no refresh.

| Area | Methods |
|---|---|
| Assets | `create_asset`, `get_asset`, `list_assets`, `delete_asset` |
| Policies | `create_policy`, `list_policies`, `delete_policy` |
| Contract definitions | `create_contract_definition`, `list_contract_definitions`, `delete_contract_definition` |
| Catalogue | `request_catalog` |
| Negotiation | `start_negotiation`, `get_negotiation`, `poll_negotiation`, `terminate_negotiation`, `resume_negotiation`, `query_negotiations` |
| Transfer | `start_transfer`, `get_transfer`, `poll_transfer`, `terminate_transfer`, `list_transfers`, `query_transfers` |
| Agreements | `get_agreement`, `query_agreements` |
| EDR | `get_edr` |

Every id interpolated into a path is percent-encoded with no safe characters — asset ids in
this platform are URLs, and that is what keeps one addressable as a single path segment.

### One method is not upstream EDC

`resume_negotiation` posts to `/dataspaces/negotiations/{id}/resume`, which is served by this
repository's [`edc-extensions`](../edc-extensions.md) on the Management context. It is the same
credential because it is on the same context — but it exists only because that extension is
loaded.

## The models, and what they invent

The models are not pass-throughs. Several fields are supplied by the client rather than by the
caller, and knowing which matters when a request does something unexpected.

| Synthesised | Where |
|---|---|
| `protocol: dataspace-protocol-http:2025-1` | every catalogue, negotiation and transfer request |
| a whole ODRL `Offer` — assigner, target, empty permission list | when a negotiation is started with no explicit policy |
| an `assetsSelector` matching every asset | when a contract definition is created with no selector |
| `dataDestination: {type: HttpProxy}` and `transferType: HttpData-PULL` | every transfer request |
| `proxyPath: "false"`, `proxyQueryParams: "true"` — **strings, not booleans** | every `DataAddress` |
| `auth_type: "bearer"`, and empty strings for a missing `endpoint` or `authorization` | when reading an EDR |
| state `"TIMEOUT"` — **a state no EDC produces** | when either polling loop expires |

That last one is the one to watch: a poll that times out returns a `TIMEOUT` state rather than
raising, so a caller comparing against real EDC state names must handle it.

### Names for the same concept

EDC and its events use several names for one identifier, and the client normalises some but not
all of them:

| Concept | Names seen |
|---|---|
| the agreement, on a negotiation event | `contractAgreementId` — the id **local to one runtime** |
| the agreement, shared by both participants | `dspAgreementId` — **not exposed by the model**; the connector reads it out of the raw payload |
| the agreement, on a transfer event | `contractId` |

The shared `dspAgreementId` is the one a data-plane request must carry, because it is the only
id both sides can name.

## Polling

```python
state = await client.poll_negotiation(negotiation_id, poll_interval=2.0, timeout=120.0)
```

| Loop | Returns on | Also returns on |
|---|---|---|
| `poll_negotiation` | `FINALIZED`, `VERIFIED`, `AGREED` — carrying the agreement id | `TERMINATED`, `ERROR` — carrying the error detail |
| `poll_transfer` | `STARTED` | `COMPLETED`, `TERMINATED`, `ERROR`, `DEPROVISIONING_REQUESTED` |

Both advance their elapsed counter by the poll interval and do not account for request latency,
so the real deadline is a little later than the `timeout` argument.

## Error conventions

Two, and they are not interchangeable.

| Convention | Methods | Behaviour |
|---|---|---|
| body-preserving | `create_asset`, `create_policy`, `create_contract_definition`, `terminate_negotiation`, `resume_negotiation` | logs and raises with the status **and the first 500 characters of EDC's response body** |
| bare | everything else | raises with the status line only |

The first is what lets the connector's sync distinguish a `409` — an asset that already has
agreements, and must be kept — from a real failure.

Some statuses are deliberately swallowed:

| Method | Treated as success |
|---|---|
| all three `delete_*` | `404` — so a first sync does not fail |
| `terminate_negotiation` | `404`, `409` |
| `terminate_transfer` | `404`, `405` |
| `resume_negotiation` | `404` — returns a synthesised "not found" result |

## Configuration

The library reads **no environment variables and no files**. Everything arrives as a
constructor or method argument.

| Argument | Supplied by the connector from |
|---|---|
| `base_url` | `EDC_PROVIDER_MANAGEMENT_URL` / `EDC_CONSUMER_MANAGEMENT_URL` |
| `api_key` | `EDC_API_KEY`, or the contents of `EDC_API_KEY_FILE` |
| `poll_negotiation(poll_interval, timeout)` | `CONNECTOR_NEGOTIATION_POLL_INTERVAL`, `CONNECTOR_NEGOTIATION_TIMEOUT` |
| `poll_transfer(timeout)` | `CONNECTOR_TRANSFER_TIMEOUT` |

The base URL is the management context root, so `/v3/assets` resolves to
`/management/v3/assets`.

## Where it fits

```
ds-connector ──► ds_edc ──► EDC Management API (X-Api-Key)
                              ├─ v3 CRUD, upstream
                              └─ /dataspaces/negotiations/{id}/resume, from edc-extensions
```

The consumer-side exchange uses six of its methods in sequence: `request_catalog` →
`start_negotiation` → `poll_negotiation` → `start_transfer` → `poll_transfer` → `get_edr`.
The provider-side sync uses the delete-then-create pair on all three object types.

It ships inside the `ds-connector` image; it is never deployed on its own.
