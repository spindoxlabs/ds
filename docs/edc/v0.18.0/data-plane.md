# EDC 0.18.0 — data plane

How a transfer process reaches something that moves bytes, and how a consumer gets a token
to pull with. Paths are relative to the `Connector` repository at `v0.18.0`; `.../` elides
the Java package path.

!!! warning "The EDC data plane is deprecated in 0.18.0"
    `DataPlaneFrameworkExtension`
    (`core/data-plane/data-plane-core/.../framework/DataPlaneFrameworkExtension.java`) is
    `@Deprecated(since = "0.16.0")` and logs at startup: *"The EDC Data Plane has been
    deprecated, the related modules will be removed in future releases, please look into Data
    Plane Signaling specification and implement your own Data Planes. The EDC control-plane is
    already supporting that specification, by adding the `data-plane-signaling` module to your
    runtime and removing the legacy `transfer-data-plane-signaling` one."*
    The HTTP proxy ("public API") was deprecated earlier (DR
    `2025-02-07-http-proxy-data-plane-deprecation`) and **no `data-plane-public-api` module
    exists** in 0.18.0.

## Two signalling stacks

The control plane talks to a data plane through one `DataFlowController`
(`spi/control-plane/transfer-spi/.../flow/DataFlowController.java`; DR
`2026-01-08-inline-data-flow-manager` removed `DataFlowManager`). 0.18.0 ships two
implementations, one per stack.

| | **Data Plane Signaling protocol** (current) | **Legacy EDC control API** (deprecated) |
|---|---|---|
| Control-plane modules | `data-protocols/data-plane-signaling/{data-plane-signaling-core, -oauth2, -spi}` | `extensions/control-plane/transfer/transfer-data-plane-signaling` (`@Deprecated(since = "0.16.0")`), `extensions/data-plane/data-plane-signaling/data-plane-signaling-client` |
| Flow controller | `DataPlaneSignalingFlowController` (`.../signaling/logic/`) | `LegacyDataPlaneSignalingFlowController` (`.../transfer/dataplane/flow/`) |
| Messages | own classes in `.../signaling/domain/`: `DataFlowPrepareMessage`, `DataFlowStartMessage`, `DataFlowStatusMessage`, `DataPlaneRegistrationMessage`, `DspDataAddress` … | core-spi `DataFlowStartMessage`, `DataFlowProvisionMessage` (`spi/common/core-spi/.../types/domain/transfer/`) |
| Data-plane endpoint | `POST {endpoint}/prepare`, `/start`, `/{id}/suspend`, `/resume`, `/terminate`, `/started`, `/completed` (`DataPlaneSignalingClient`) | `/v1/dataflows` on the data plane's `control` context: `prepare`, `start`, `{id}/start`, `{id}/state`, `{id}/terminate`, `{id}/suspend`, `check` (`DataPlaneSignalingApiController`, `data-plane-signaling-api`) |
| Data plane → control plane | `POST /transfers/{id}/dataflow/{prepared,started,completed,errored}` on the `signaling` context (`DataPlaneTransferApiController`), guarded by `DataPlaneTransferAuthorizationFilter` (caller must be the transfer's data plane) | `TransferProcessControlApiController`, `/transferprocess/{id}/complete · fail · provisioned` on `control` (`extensions/control-plane/api/control-plane-api`) |
| Authentication | per data plane `authorizationProfile`, via `SignalingAuthorization`; `oauth2_client_credentials` built in (`data-plane-signaling-oauth2`) | `ControlClientAuthenticationProvider` (no-op default) and the `control` context's auth filter |
| Registration | Management API `PUT /v4/dataplanes` (single participant) or `/v5beta/participants/{id}/dataplanes`, body `DataPlaneRegistrationMessage{dataplaneId, endpoint, transferTypes, labels, authorization}` | `DataPlaneSelectorService.register` — in-process when the selector is embedded, otherwise `POST` to `edc.dpf.selector.url` (the control plane's `/v1/dataplanes` on `control`) |
| In BOM | `controlplane-base-bom`, `controlplane-virtual-base-bom` | `controlplane-base-bom` has only the legacy **client**; `transfer-data-plane-signaling` is in `federatedcatalog-base-bom`; the legacy data-plane API is in `dataplane-base-bom` |

`signaling` context settings (`.../signaling/SignalingApiConfiguration.java`):
`web.http.signaling.port` (8182), `web.http.signaling.path` (`/api/signaling`),
`web.http.signaling.public.uri` — the callback address sent to data planes.

Both flow-controller extensions use a plain `@Provider`; with both on the classpath the later
registration replaces the earlier (see [Runtime model](index.md#dependency-injection)). Which
one wins was not verified.

DR `2023-12-12-dataplane-signaling` records the decision to implement the protocol; the spec
document it links is not in the 0.18.0 tree.

### Legacy client: embedded or remote

`LegacyDataPlaneSignalingClientExtension` (`data-plane-signaling-client`) uses an
`EmbeddedDataPlaneClient` — an in-process call — when a `DataPlaneManager` is in the same
runtime, and `LegacyDataPlaneSignalingClient` (HTTP) otherwise.

## Selecting a data plane

`DataPlaneSelectorService` (`spi/data-plane-selector/data-plane-selector-spi/`), implemented by
`EmbeddedDataPlaneSelectorService`
(`core/data-plane-selector/data-plane-selector-core/.../service/`). DR
`2025-07-09-embed-data-plane-selector`: selection runs **only embedded** in the control plane;
`RemoteDataPlaneSelectorService.select` refuses.

`selectFor(transferProcess)` keeps instances that belong to the transfer's participant
context, are not `UNREGISTERED`, list the transfer type in `allowedTransferTypes`, and carry
all of the asset's `dataplaneMetadata` labels; then applies the strategy
(`edc.dataplane.client.selector.strategy`, default `random`; `SelectionStrategyRegistry`).
The legacy controller uses the older `select(strategy, predicate)`.

`DataPlaneInstance` (`.../selector/spi/instance/DataPlaneInstance.java`): `url`,
`allowedTransferTypes`, `allowedSourceTypes`, `destinationProvisionTypes`, `labels`,
`authorizationProfile`, `participantContextId`, `properties`, `lastActive`. DR
`2026-02-10-data-plane-selector-manager-dismission` removed the heartbeat manager.

Self-registration (`extensions/data-plane/data-plane-self-registration/`,
`DataplaneSelfRegistrationExtension`) registers the running data plane in `start()`: id =
`edc.component.id`, url = control API URL + `/v1/dataflows`, source types from the pipeline,
transfer types `<type>-PULL` for each EDR type and `<type>-PUSH` for each sink type. Fails
startup if registration fails. `edc.data.plane.self.unregistration` (default false).

## The data-plane framework (deprecated)

`core/data-plane/data-plane-core`, SPI `spi/data-plane/data-plane-spi`.

- `DataPlaneManager` / `DataPlaneManagerImpl` — a state machine over `DataFlow` entities.
  States (`DataFlowStates`): `PROVISIONING(25)`, `PROVISION_REQUESTED(40)`,
  `PROVISION_NOTIFYING(45)`, `PROVISIONED(50)`, `RECEIVED(100)`, `STARTED(150)`,
  `COMPLETED(200)`, `SUSPENDED(225)`, `TERMINATED(250)`, `FAILED(300)`, `NOTIFIED(400)`,
  `DEPROVISIONING(500)`, `DEPROVISION_REQUESTED(550)`, `DEPROVISIONED(600)`,
  `DEPROVISION_FAILED(700)`.
- **PULL** flows: create an EDR via `EndpointDataReferenceServiceRegistry`, go to `STARTED`;
  no `TransferService` runs. **PUSH** flows: go to `RECEIVED` and run a
  `TransferService`.
- `PipelineService` with `DataSourceFactory` / `DataSinkFactory` per type; `TransferService`s
  are resolved by priority (DR `2025-03-14-prioritized-transfer-services`).
- Provisioning lives here (DR `2025-02-27-move-provisioning-phase-data-plane`):
  `Provisioner`, `ProvisionerManager`, `ResourceDefinitionGenerator` (`.../spi/provision/`);
  example `extensions/data-plane/data-plane-provision-http`.
- Built-in sources/sinks: HTTP (`data-plane-http`), Kafka (`data-plane-kafka`, in no BOM); `data-plane-http-oauth2`
  fetches client-credentials tokens for HTTP sources/sinks and, per its README, supports
  neither expiry nor refresh.

Defaults (`DataPlaneDefaultServicesExtension`): in-memory `DataPlaneStore` and
`AccessTokenDataStore`, and a **`NoOpDataPlaneAuthorizationService` that logs it "won't support
PULL transfer types"** unless `data-plane-iam` replaces it.

## Pull: the EDR and its token

`extensions/data-plane/data-plane-iam/`:

- `DataPlaneIamExtension` registers `DataPlaneAuthorizationServiceImpl` as the EDR service for
  `HttpData` (destination and response channel) and as `DataPlaneAuthorizationService`.
- `DataPlaneAuthorizationServiceImpl.createEndpointDataReference(DataFlow)`:
  `PublicEndpointGeneratorService.generateFor(destType, source)` gives the endpoint;
  `DataPlaneAccessTokenService.obtainToken(...)` gives the token. The resulting `DataAddress`
  has `edc:endpoint`, `edc:endpointType`, `edc:authorization`, plus response-channel variants.
  Token claims include `agreement_id`, `asset_id`, `process_id`, `flow_type`, `participant_id`.
- `DefaultDataPlaneAccessTokenServiceImpl`: JWT signed with the key at
  `edc.transfer.proxy.token.signer.privatekey.alias`, `kid` =
  `edc.transfer.proxy.token.verifier.publickey.alias`, a `jti`; stores
  `AccessTokenData(id, claimToken, dataAddress, additionalProperties)`
  (`spi/data-plane/data-plane-spi/.../AccessTokenData.java`) in the `AccessTokenDataStore`.
  Validation requires `sub == iss` and a `jti`. Tokens can be revoked per transfer.
- `authorize(token, requestData)` resolves the stored token data and asks
  `DataPlaneAccessControlService.checkAccess`, whose default **always allows**.

**No production module registers an endpoint generator.** `PublicEndpointGeneratorService`
(`.../spi/iam/PublicEndpointGeneratorService.java`) starts empty; only tests call
`addGeneratorFunction`. Without one, `generateFor` fails with *"No Endpoint generator function
registered for transfer type destination 'HttpData'"*
(`core/data-plane/data-plane-core/.../framework/PublicEndpointGeneratorServiceImpl.java`), so a
pull transfer needs an extension that registers a generator.

The token is **EDC's own**, not a DCP artefact: whoever serves the endpoint has to validate it
(e.g. through `DataPlaneAuthorizationService.authorize`, or by verifying the JWT against the
verifier key) — the upstream proxy that used to do this is gone.

### How the EDR reaches the consumer

1. Provider `TransferProcessorsImpl.processStarting` sends a `TransferStartMessage` whose
   `dataAddress` is the stored EDR (`spi/control-plane/transfer-spi/.../protocol/TransferStartMessage.java`).
2. The consumer's transfer process moves to `STARTED` and emits `TransferProcessStarted`
   with the data address.
3. `EndpointDataReferenceStoreReceiver`
   (`extensions/control-plane/edr/edr-store-receiver/`) stores an
   `EndpointDataReferenceEntry` and the `DataAddress` for **consumer** transfers, and deletes
   them on completed / suspended / terminated. `edc.edr.receiver.sync` (default false) selects
   a sync subscription.
4. Clients read it through the v3 EDR API (`/v3/edrs`, `EdrCacheApiV3Controller`) or the
   `EndpointDataReferenceStore` SPI (`spi/common/edr-store-spi`).
5. **Or, with no cache at all**, from the event itself: a transfer request's
   `callbackAddresses` receive `TransferProcessStarted`, data address included. That is the
   only path v5 leaves, and it is the one ds uses (see
   [Management API](management-api.md#the-edr-without-an-edr-api)).

DR `2026-04-09-edr-cache-deprecation`: the EDR cache is deprecated — the SPI types are
`@Deprecated(since = "management-api:v3")` and there is no v4 EDR API — because EDR handling
moves to the data plane under the Data Plane Signaling protocol. No EDR refresh mechanism
exists in 0.18.0.

## Transfer types

`TransferType(destinationType, flowType, responseChannelType)`
(`spi/common/core-spi/.../types/domain/transfer/TransferType.java`), serialised
`<dest>-<PUSH|PULL>[-<response>]`, parsed by `TransferTypeParserImpl`. The response channel
(DR `2024-10-24-bidirectional-data-transfers`) is an optional second endpoint the provider
exposes for consumer feedback; `DataPlaneManagerImpl` and `DataPlaneAuthorizationServiceImpl`
handle it. See [Control plane](control-plane.md#transfer-type-push-and-pull).

## Integrating an external data plane (current stack)

From the code (the protocol document is not in the tree):

1. expose `POST {endpoint}/prepare` and `/start` returning a `DataFlowStatusMessage`, plus
   `/{processId}/suspend`, `/resume`, `/terminate`, `/started`, `/completed`;
2. register with a `DataPlaneRegistrationMessage` through the Management API, including an
   authorisation profile;
3. report progress to `<web.http.signaling.public.uri>/transfers/{transferId}/dataflow/…`,
   authenticated per that profile;
4. for pull, return the endpoint and credentials in the start response's `dataAddress` — the
   control plane forwards it in the DSP `TransferStartMessage`.

## What ds adds on top

ds's `services/edc-connector/build.gradle.kts` **excludes** `data-plane-signaling`,
`-core` and `-oauth2` from `controlplane-dcp-bom` and **adds** `transfer-data-plane-signaling`
— the opposite of what the deprecation warning above recommends — and packages
`dataplane-base-bom` in the same runtime, so the legacy client signals the data plane
in-process. This is deliberate: in 0.18.0 `dataplane-base-bom` still serves the pre-DPS,
JSON-LD control API, so the DPS client and EDC's own data plane do not interoperate, and
EDC ships no DPS data-plane server. Adopting DPS needs a data plane that speaks it — a
capability decision, recorded in the build file, not part of a version bump. `services/edc-extensions/.../HttpDataEndpointExtension.java` registers the
`HttpData` endpoint generator that upstream does not ship. See
[edc-connector](../../services/edc-connector.md).
