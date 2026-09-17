# ds-edc

`import ds_edc`

A typed async client for the **EDC Management API v5** (`v5beta` at EDC 0.18.0), plus the
Pydantic models for its request and response shapes and the callback event that carries a
consumer's EDR.

It owns the JSON-LD the platform sends to an EDC control plane: the `@context`, the `@type`,
the camelCase field names, the compact ODRL form v5 validates, and the DSP protocol identifier.
It also owns the polling loops that turn EDC's asynchronous negotiation and transfer state
machines into a single awaited result.

It holds no state and reads no configuration. It is constructed per participant context with a
base URL, the context id and a token source, all supplied by its caller.
[`services/connector`](../connector.md) is its only real consumer.

!!! note "Not to be confused with `helm/charts/ds-edc`"
    That chart deploys the [EDC connector runtime](../edc-connector.md). This is a Python
    library that talks to one.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Data Exchange](../../blueprints/dssc/data-interoperability/data-exchange.md) |
| Rules it enforces | [Rulebook · Data exchange](../../rulebook/data-exchange.md) — the protocol version pin |
| Decision | [ADR-0014](../../decisions/ADR-0014-management-api-v5-and-the-organisation-actor.md) |

## The protocol pin lives here

```python
DATASPACE_PROTOCOL = "dataspace-protocol-http:2025-1"
```

That string occurs **once in the repository**, and it is sent on every catalogue, negotiation
and transfer request. Changing it is a dataspace-wide breaking change: every counterparty must
speak the same version.

## What it covers

```python
EdcManagementClient(
    base_url,                    # the management context root, e.g. http://edc-rec:19193/management
    participant_context_id,      # this participant's context in the EDC, its DID in ds
    token_source=...,            # async () -> str; a bearer from the organisation client
    api_version="v5beta",        # "v5" from EDC 0.19
)
```

Every resource path is `/{api_version}/participants/{participant_context_id}/…`. The version is
one setting (`EDC_MANAGEMENT_API_VERSION` in the connector), so the upgrade to 0.19 changes a
string. **There is no API key.** Each request carries a bearer token from `token_source`. If EDC
answers `401`, the source is told to drop its cached token (when it has an `invalidate()`
method) and the request is sent once more.

EDC checks the token's signature, issuer, `sub` (the participant context) and `scope`
(`management-api:<resource>:read|write`). It never checks the audience, so anyone holding the
token can call the management API wherever its port can be reached. For how the platform deals
with that, see [ADR-0014](../../decisions/ADR-0014-management-api-v5-and-the-organisation-actor.md).

| Area | Methods |
|---|---|
| Assets | `create_asset`, `get_asset`, `list_assets`, `delete_asset` |
| Policies | `create_policy`, `list_policies`, `delete_policy` |
| Contract definitions | `create_contract_definition`, `list_contract_definitions`, `delete_contract_definition` |
| Catalogue | `request_catalog` |
| Negotiation | `start_negotiation`, `get_negotiation`, `poll_negotiation`, `terminate_negotiation`, `resume_negotiation`, `query_negotiations` |
| Transfer | `start_transfer`, `get_transfer`, `poll_transfer`, `terminate_transfer`, `list_transfers`, `query_transfers`, `find_transfer_by_correlation` |
| Agreements | `get_agreement`, `query_agreements` |

Every id put into a path is percent-encoded with no safe characters. Asset ids on this platform
are URLs, and the encoding keeps each one a single path segment.

### No EDR method

EDC 0.18.0's v5 has no EDR endpoint (upstream decision record
`2026-04-09-edr-cache-deprecation`). The consumer gets its EDR from the transfer's **own
callback**:

1. `TransferRequest(callback_addresses=[CallbackAddress(...)])` names a URL and the
   `transfer.process.started` event.
2. EDC posts `TransferProcessStarted` to that URL.
3. `ds_edc.webhooks.TransferProcessStartedEvent` parses the post, and `.edr()` returns the
   `EdrResponse`.

The connector stores the EDR it receives (see [connector](../connector.md#the-edr-arrives-on-a-callback)).

`CallbackAddress.auth_key` is the **name** of the header EDC sends. `auth_code_id` is the
**vault alias** of that header's value, which EDC reads from its own vault, so the value never
travels in the request.

!!! warning "Upstream gap: `authKey` and `authCodeId` must be prefixed"
    The v2 management context maps `uri`, `events` and `transactional` on a callback address,
    but not `authKey` or `authCodeId` (EDC 0.18.0 and main). Sent bare, both keys expand to
    nothing and are dropped without an error, and EDC calls back with no header at all
    (measured). The client sends `edc:authKey` and `edc:authCodeId`, which the context does
    resolve.

### One method is not upstream EDC

`resume_negotiation` posts to `/dataspaces/negotiations/{id}/resume`, which this repository's
[`edc-extensions`](../edc-extensions.md) serves on the management context. It takes the same
bearer token and requires `management-api:negotiations:write`. It has no version or context
segment, because the classic runtime holds exactly one context.

## The models, and what they supply

The models are not pass-throughs. Some fields come from the client rather than the caller, and
it helps to know which ones when a request does something unexpected.

| Supplied | Where |
|---|---|
| `@context: ["https://w3id.org/edc/connector/management/v2"]`, **as an array** | every body — v5 answers `400` to a JSON-object context |
| `protocol: dataspace-protocol-http:2025-1` | every catalogue, negotiation and transfer request |
| the policy rewritten into the DSP 2025 compact form (`ds_edc.odrl.to_dsp_compact`) | every policy definition and every negotiation offer |
| `@type: Criterion` on each selector entry, and a selector matching every asset when none is given | contract definitions and queries |
| `transferType: HttpData-PULL` | every transfer request |
| `proxyPath: "false"`, `proxyQueryParams: "true"` — **strings, not booleans** | every `DataAddress` |
| `auth_type: "bearer"` when EDC omits it | when reading an EDR |

v5 validates the **raw** body against JSON schemas before any JSON-LD processing. The DSP
schema requires a policy to have `@type` `Set` (or `Offer`), bare `permission`, `action`,
`constraint`, `leftOperand` and `operator` keys, and an operator from the profile's list.
`to_dsp_compact` expands every compact IRI against the document's own context and drops that
context. It raises `OdrlConversionError` for an operator the profile has no term for. The
meaning of the policy is unchanged: the permissions EDC stores are identical to what v3 stored
(measured).

A negotiation needs the offer's `odrl_policy` taken from the provider's catalogue. The client
no longer builds an empty offer, because DSP matches the offer against what was published and a
hand-built one could never match.

### Names for the same concept

EDC and its events use several names for the same identifier. The client normalises some of
them, but not all:

| Concept | Names seen |
|---|---|
| the agreement, on a negotiation event | `contractAgreementId` — the id **local to one runtime** |
| the agreement, shared by both participants | `dspAgreementId` — **not exposed by the model**; the connector reads it out of the raw payload |
| the agreement, on a transfer or its callback | `contractId` |
| the consumer's transfer id, as the provider holds it | `correlationId` — `find_transfer_by_correlation` |

A data-plane request must carry the shared `dspAgreementId`, because it is the only agreement id
both sides can name.

## Polling

```python
state = await client.poll_negotiation(negotiation_id, poll_interval=2.0, timeout=120.0)
```

| Loop | Returns on | Also returns on |
|---|---|---|
| `poll_negotiation` | `FINALIZED`, `VERIFIED`, `AGREED` — carrying the agreement id | `TERMINATED` — carrying the error detail |
| `poll_transfer` | `STARTED` | `COMPLETED`, `TERMINATED`, `DEPROVISIONING_REQUESTED` |

Both loops measure a monotonic deadline. When the deadline passes they raise `EdcPollTimeout`,
which carries the last state they observed. They do not return a synthetic state.

## Error conventions

Every method passes a failed response through one helper. It logs the failure and raises
`httpx.HTTPStatusError` with the status **and the first 500 characters of EDC's body**.

Some statuses are handled rather than raised:

| Method | Handling |
|---|---|
| all three `delete_*` | `404` is success — the requested end state |
| `terminate_negotiation`, `terminate_transfer` | `409` is success only when the entity is already `TERMINATED`; otherwise it raises |
| `resume_negotiation` | `404` returns a "not found" result |
| `find_transfer_by_correlation` | no match returns `None` |

## Configuration

The library reads **no environment variables and no files**. Everything arrives as a
constructor or method argument.

| Argument | Supplied by the connector from |
|---|---|
| `base_url` | `EDC_MANAGEMENT_URL` |
| `participant_context_id` | `EDC_PARTICIPANT_CONTEXT_ID`, defaulting to `CONNECTOR_PARTICIPANT_DID` |
| `token_source` | the organisation client, `CONNECTOR_CLIENT_ID` / `CONNECTOR_CLIENT_SECRET` |
| `api_version` | `EDC_MANAGEMENT_API_VERSION` |
| `CallbackAddress` | `CONNECTOR_EDC_CALLBACK_URL`, `CONNECTOR_EDC_CALLBACK_AUTH_CODE_ID` |
| `poll_negotiation(poll_interval, timeout)` | `CONNECTOR_NEGOTIATION_POLL_INTERVAL`, `CONNECTOR_NEGOTIATION_TIMEOUT` |
| `poll_transfer(poll_interval, timeout)` | `CONNECTOR_TRANSFER_POLL_INTERVAL`, `CONNECTOR_TRANSFER_TIMEOUT` |

## Where it fits

```
ds-connector ──► ds_edc ──► EDC Management API v5beta (OAuth2 bearer, sub = context)
     ▲                        ├─ v5 resources, upstream
     │                        └─ /dataspaces/negotiations/{id}/resume, from edc-extensions
     └── POST /webhooks/edc-callback ◄── TransferProcessStarted (the EDR)
```

The consumer-side exchange calls, in order:

1. `request_catalog`
2. `start_negotiation`
3. `poll_negotiation`
4. `start_transfer`, with a callback
5. `poll_transfer`

The EDR then arrives on the callback. The provider-side sync uses the delete-then-create pair on
all three object types.

It ships inside the `ds-connector` image and is never deployed on its own.
