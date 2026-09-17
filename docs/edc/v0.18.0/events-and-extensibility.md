# EDC 0.18.0 — events and extensibility

What an extension can observe, where it can plug in, and how state is persisted. Paths are
relative to the `Connector` repository at `v0.18.0`; `.../` elides the Java package path.

## Events

`EventRouter` (`spi/common/core-spi/.../spi/event/EventRouter.java`):

| Method | Delivery |
|---|---|
| `registerSync(Class<E>, EventSubscriber)` | inline, in the publisher's thread, so it runs before the state machine moves on; an exception propagates to the publisher |
| `register(Class<E>, EventSubscriber)` | asynchronous; failures are logged as severe and dropped |
| `publish(E)` / `publish(EventEnvelope)` | |

`EventRouterImpl` (`core/common/runtime-core/.../event/EventRouterImpl.java`) matches
subscribers by `isAssignableFrom`, so subscribing to `Event.class` receives everything. The
async executor is `Executors.newFixedThreadPool(1)` (`RuntimeCoreServicesExtension`) — one
thread for all async subscribers. An `EventEnvelope` carries `id`, `at` and `payload`.

Event types:

| Family | Events | Package |
|---|---|---|
| `ContractNegotiationEvent` | Initiated, Requested, Offered, Accepted, Agreed, Verified, Finalized, Terminated | `spi/control-plane/contract-spi/.../event/contractnegotiation/` |
| `TransferProcessEvent` | Initiated, PreparationRequested, Prepared, Provisioned, Requested, Started, Suspended, Resumed, Completed, Terminated, DeprovisioningRequested, Deprovisioned | `spi/control-plane/transfer-spi/.../event/` |
| `AssetEvent`, `PolicyDefinitionEvent`, `ContractDefinitionEvent`, `SecretEvent` | Created, Updated, Deleted | respective SPI modules |

State-machine listeners are bridged to events by `ContractNegotiationEventListener`,
`TransferProcessEventListener` and the entity `*EventListener`s in
`core/control-plane/control-plane-aggregate-services/`.

Out-of-process publishers:

- `extensions/common/events/events-cloud-http` — CloudEvents over HTTP to
  `edc.events.cloudevents.endpoint` (required), async, all events.
- `extensions/common/events/events-nats` — publishes to a NATS stream
  (`edc.events.nats.url`, `.stream`, `.stream.create`, `.stream.create.force`), async.

Neither is in a BOM listed on the [runtime page](index.md#distributions-the-boms).

## Callbacks

A `CallbackAddress` (`spi/common/core-spi/.../domain/callback/CallbackAddress.java`) — `uri`,
`events`, `transactional`, `authKey`, `authCodeId` — asks EDC to POST events to a URL.

- **Per request**: the Management API accepts `callbackAddresses` on a contract request and a
  transfer request; they are stored on the entity (`ContractRequest.CALLBACK_ADDRESSES`,
  `TransferRequest.TRANSFER_REQUEST_CALLBACK_ADDRESSES`).
- **Static**: `edc.callback.<alias>.uri`, `.events` (comma-separated), `.transactional`
  (default false), `.auth.key`, `.auth.codeid`
  (`extensions/control-plane/callback/callback-static-endpoint/`). The hyphenated
  `auth-key` / `auth-code-id` keys are deprecated since 0.17.0.

`callback-event-dispatcher` (`extensions/control-plane/callback/callback-event-dispatcher/`)
subscribes twice to `Event.class`: synchronously for `transactional = true` callbacks, whose
failure throws an `EdcException` in the publisher's thread, and asynchronously for the rest. An event matches
when its name **starts with** a configured event string, so `contract.negotiation` matches
every negotiation event. `authCodeId` is resolved from the `Vault` and sent in a header whose
name is `authKey` (`CallbackHttpClient`). Both modules are in `controlplane-base-bom`.

## State-machine hooks

| Hook | Where | Use |
|---|---|---|
| `ContractNegotiationListener` | `spi/control-plane/contract-spi/.../negotiation/observe/` — `initiated`, `requested`, `offered`, `accepted`, `terminating`, `terminated`, `agreed`, `verified`, `finalized` | react in-process, registered on `ContractNegotiationObservable` |
| `TransferProcessListener` | `spi/control-plane/transfer-spi/.../observe/` — `initiated` … `started(tp, TransferProcessStartedData)` … `terminated`, `suspended`, `resumed` … | same, on `TransferProcessObservable` |
| `ContractNegotiationPendingGuard`, `TransferProcessPendingGuard` | `PendingGuard<E> extends Predicate<E>` (`spi/common/core-spi/.../entity/PendingGuard.java`) | hold an entity for an external decision (DR `2023-07-20-state-machine-guards`) |
| `ParticipantAgentServiceExtension` | `spi/common/participant-spi` | add attributes to every `ParticipantAgent` |

The `pre*` listener methods (DR `2025-06-20-listeners-pre-methods`) are gone in 0.18.0.

A guard is wired with `.guard(pendingGuard, this::setPending)` in the managers
(`AbstractContractNegotiationManager`, `TransferProcessManagerImpl`): when it matches, the
entity is saved with `pending = true` and later batches skip it. Clearing the flag is up to
the extension; the default guards (`ContractNegotiationDefaultServicesExtension`,
`TransferProcessDefaultServicesExtension`) never match.

### The state-machine library

`core/common/lib/state-machine-lib/.../statemachine/`: `StateMachineManager` loops over
`ProcessorImpl`s, each fetching a batch of entities in one state (leased) and processing them.
`RetryProcessor` (DR `2025-02-05-state-machine-retry-processor-refactor`) chains steps with
`doProcess`, `onSuccess`, `onFailure`, `onFinalFailure`. Configuration per context
(`edc.negotiation`, `edc.transfer`, `edc.dataplane`, `edc.policy.monitor`):
`<ctx>.state-machine.iteration-wait-millis`, `.state-machine.batch-size`,
`.send.retry.limit`, `.send.retry.base-delay.ms`.

**Leases** make this safe with several replicas: `StateEntityStore.nextNotLeased`,
`findByIdAndLease`, `breakLease` (`spi/common/core-spi/.../persistence/StateEntityStore.java`).
The SQL lease table is `edc_lease` (`extensions/common/sql/sql-lease-spi/.../LeaseStatements.java`),
default lease 60 s (`SqlLeaseContext`). The random `runtimeId` assigned at boot is the lease
holder ([Runtime model](index.md#the-extension-lifecycle)).

The virtual control plane replaces polling with **tasks** (`spi/common/task-spi`,
`core/common/task-core`, `extensions/common/store/sql/task-store-sql`, NATS transport under
`extensions/control-plane/tasks/nats/`); see
[Control plane](control-plane.md#two-execution-models).

## Extension points

Before writing something, check this list.

| To… | Register with | SPI |
|---|---|---|
| decide a policy constraint | `PolicyEngine.registerFunction` + `RuleBindingRegistry.bind` | `spi/common/policy-engine-spi` — [Policy engine](policy-engine.md) |
| check a whole policy | `PolicyEngine.registerPreValidator` / `registerPostValidator` | same |
| add a scope | `PolicyEngine.registerScope` with a `PolicyContext` subclass | same |
| validate Management API input | `JsonObjectValidatorRegistry.register(type, Validator<JsonObject>)` (DR `2023-06-05-validation-engine`) | `spi/common/validator-spi` |
| validate a data address | `DataAddressValidatorRegistry.registerSourceValidator` / `registerDestinationValidator` | same; example `extensions/common/validator/validator-data-address-http-data` |
| convert JSON-LD ⇄ objects | `TypeTransformerRegistry.register`, `forContext(...)` (DR `2024-11-19-transformer-version-scheme`) | `spi/common/transform-spi` |
| add JSON-LD terms | `JsonLd.registerNamespace(prefix, iri, scope)`, `registerContext`, `registerCachedDocument` (DR `2023-10-04-json-ld-scopes`) | `spi/common/json-ld-spi` |
| authenticate an API context | an `ApiAuthenticationProvider` in `ApiAuthenticationProviderRegistry` | `spi/common/auth-spi` — [Management API](management-api.md) |
| add a REST resource | `WebService.registerResource(contextAlias, resource)` | `spi/common/web-spi` |
| send protocol messages | `ProtocolRemoteMessageDispatcher` — replaces `RemoteMessageDispatcherRegistry` (DR `2026-06-10-remove-dispatcher-registry`) | `spi/control-plane/control-plane-spi/.../protocol/` |
| resolve the local participant id | `ParticipantIdentityResolver` | `spi/common/connector-participant-context-spi` |
| change which credentials are requested | `ScopeExtractor` in `ScopeExtractorRegistry`, or `edc.iam.dcp.scopes.*` | `spi/common/decentralized-claims-spi` — [Identity and trust](identity-and-trust.md#scopes) |
| customise the presentation request | replace the default `PresentationRequestService` | same |
| sign JWTs differently | `JwsSignerProvider` (DR `2024-08-05-custom-jwssigners`) | `spi/common/jwt-spi` |
| store secrets | a `Vault` (partition-aware overloads) | `spi/common/boot-spi/.../security/Vault.java`; `vault-hashicorp` |
| move data | `DataSourceFactory` / `DataSinkFactory`, `TransferService`, `Provisioner` (deprecated framework) or an external data plane | [Data plane](data-plane.md) |
| produce an EDR endpoint | `PublicEndpointGeneratorService.addGeneratorFunction` | `spi/data-plane/data-plane-spi/.../iam/` |
| authorise pull requests | `DataPlaneAccessControlService` | `extensions/data-plane/data-plane-iam` |
| parse transfer types | `TransferTypeParser` | `spi/control-plane/transfer-spi/.../flow/` |
| log | `Monitor` / `MonitorExtension` | `spi/common/boot-spi/.../monitor/` |

## Stores and SQL

Every store is an SPI with an in-memory `@Provider(isDefault = true)` and an optional SQL
module ([Runtime model](index.md#how-providers-are-ordered-and-chosen)).

| Store | In-memory default from | SQL module |
|---|---|---|
| `AssetIndex`, `ContractDefinitionStore`, `ContractNegotiationStore`, `TransferProcessStore`, `PolicyDefinitionStore` | `ControlPlaneDefaultServicesExtension` (`core/control-plane/control-plane-core`) | `extensions/control-plane/store/sql/*` (aggregated by `control-plane-sql`) |
| `DataPlaneInstanceStore` | `DataPlaneSelectorDefaultServicesExtension` | `data-plane-instance-store-sql` |
| `EndpointDataReferenceEntryIndex` | `EndpointDataReferenceStoreDefaultServicesExtension` | `edr-index-sql` |
| `PolicyMonitorStore` | `PolicyMonitorDefaultServicesExtension` | `policy-monitor-store-sql` |
| `DataPlaneStore`, `AccessTokenDataStore` | `DataPlaneDefaultServicesExtension` | `data-plane-store-sql`, `accesstokendata-store-sql` |
| `ParticipantContextStore`, `ParticipantContextConfigStore` | participant-context cores | `participantcontext-store-sql`, `participantcontext-config-store-sql` |
| `TaskStore` | `TasksDefaultServicesExtension` | `task-store-sql` |
| JTI (replay) store | — | `jti-validation-store-sql` |

The SQL extension pattern (e.g.
`extensions/control-plane/store/sql/transfer-process-store-sql/.../SqlTransferProcessStoreExtension.java`):
inject optional dialect statements (`@Inject(required = false)`, fallback
`PostgresDialectStatements`), pick the datasource by
`edc.sql.store.<store>.datasource`, get a lease context, and register the DDL resource with
`SqlSchemaBootstrapper`. The DDL is applied at boot only when **`edc.sql.schema.autocreate`**
is true (default **false**, `extensions/common/sql/sql-bootstrapper/`). Queries use `QuerySpec`
(`filterExpression`, `offset` 0, `limit` 50, `sortField`, `sortOrder`) with `Criterion`s
(`spi/common/core-spi/.../query/`); operators are extensible through
`CriterionOperatorRegistry`.

## What ds adds on top

`services/edc-extensions/.../DataspacesExtension.java` registers two **asynchronous**
`EventRouter` subscribers that forward negotiation and transfer events to the connector's
webhooks, a `ContractNegotiationPendingGuard`, policy functions and a post-validator, and a
REST resource on the management context. See
[edc-extensions](../../services/edc-extensions.md).
