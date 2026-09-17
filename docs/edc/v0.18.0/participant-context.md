# EDC 0.18.0 — participant context

How EDC 0.18.0 models "on whose behalf" a runtime acts, and how one runtime can act for
several participants. Paths are relative to the `Connector` repository at `v0.18.0` unless
another repository is named.

## The idea

DR `2025-08-26-participant-context` introduced a **participant context**: the tenant every
resource and every protocol interaction belongs to. The goal stated there is to run workloads
for several participants in one runtime ("EDC Virtual"). The Connector's classic distribution
keeps a single, implicit context; the multi-participant ("virtual") control plane is a
different set of modules in the same repository (`dist/bom/controlplane-virtual-*`).

Since that DR, the SPIs take the context explicitly:

- `IdentityService.obtainClientCredentials(participantContextId, …)` /
  `verifyJwtToken(participantContextId, …)`;
- `ProtocolRemoteMessageDispatcher.dispatch(participantContextId, …)`;
- `ContractNegotiationService.initiateNegotiation(ParticipantContext, …)`,
  `TransferProcessService.initiateTransfer(ParticipantContext, …)`;
- `ParticipantIdentityResolver.getParticipantId(participantContextId, protocol)`;
- `ProtocolWebhookResolver.getWebhook(participantContextId, protocol)`;
- `Vault.resolveSecret(vaultPartition, key)` and friends.

## The entity

`spi/common/connector-participant-context-spi/.../participantcontext/spi/types/ParticipantContext.java`:

| Field | Meaning |
|---|---|
| `id` | the participant context id (the tenant key) |
| `identity` | the participant id used on the wire (for DCP, the DID); required |
| `properties` | free-form map |
| `state` | `CREATED(100)`, `ACTIVATED(200)`, `DEACTIVATED(300)` (`ParticipantContextState`) |
| `createdAt`, `lastModified` | timestamps |

The context id and the participant identity are **separate values**. Resource ownership uses
the id; protocol messages use the identity.

`AbstractParticipantResource` (same module) gives every tenant-owned entity a
`participantContextId`. In 0.18.0 that is: `Asset`, `PolicyDefinition`, `ContractDefinition`,
`ContractNegotiation`, `ContractAgreement`, `TransferProcess`, `DataPlaneInstance`,
`EndpointDataReferenceEntry`, and `ParticipantContextConfiguration`.

Store and service: `ParticipantContextStore`, `ParticipantContextService` (same SPI), default
implementations in `core/common/participant-context-core` (`ParticipantContextServiceImpl`,
in-memory store as a default provider). SQL: `extensions/control-plane/store/sql/participantcontext-store-sql`.

## Per-participant configuration

DR `2025-10-15-participant-context-config`: configuration that used to be runtime-wide
(`edc.iam.sts.oauth.*`, the DID, …) is read per participant, and can be provisioned without a
restart. SPI: `spi/common/participant-context-config-spi/`.

- `ParticipantContextConfiguration` — `participantContextId`, `entries` (plain),
  `privateEntries` (sensitive), timestamps.
- `ParticipantContextConfig` — the read side: `getString(participantContextId, key)`,
  `getInteger`, `getLong`, `getBoolean`, and `getSensitiveString` for private entries. Throws
  if the context has no configuration.
- `ParticipantContextConfigStore` (`save(ParticipantContextConfiguration)`, `get(id)`),
  `ParticipantContextConfigService`.

`core/common/participant-context-config-core`: `ParticipantContextConfigServiceImpl.save`
**encrypts every private entry** with the algorithm named by
`edc.participants.config.encryption.algorithm` (checked in `prepare()`); `ParticipantContextConfigImpl`
decrypts on `getSensitiveString`. The only algorithm module is `aes-encryption`
(`extensions/common/encryption/aes-encryption/`), which registers `aes` when
`edc.encryption.aes.key.alias` names a vault key. SQL:
`extensions/control-plane/store/sql/participantcontext-config-store-sql`. REST (v5 only):
`/v5beta/participants/{id}/config`, admin scope.

The DR's method signatures differ from the 0.18.0 code; the code is described here.

## Classic mode: one implicit participant

`core/common/participant-context-connector-classic-core` (in `controlplane-base-bom`, not in
the virtual BOM):

| Setting | Default | Effect |
|---|---|---|
| `edc.participant.id` | `anonymous` | the context's **identity** |
| `edc.participant.context.id` | *(unset → `edc.participant.id`, with a warning)* | the context's **id** |

- `ClassicParticipantContextDefaultServicesExtension` provides a `SingleParticipantContextSupplier`
  (`spi/common/participant-context-single-spi`) that always returns this one context, and a
  `SingleParticipantContextConfigStore` that is **read-only** and exposes the **whole runtime
  configuration** as that context's entries. So `ParticipantContextConfig.getString(id, key)`
  reads the ordinary properties/environment in classic mode.
- `ClassicParticipantContextServicesExtension.prepare()` creates or updates the context in the
  store.
- Classic v3/v4 controllers stamp new entities with the supplier's context id (e.g.
  `extensions/control-plane/api/management-api/asset-api/.../BaseAssetApiController.java`).

DR `2025-08-26` on migration: the default id must be **stable across restarts**, and rows
written before the upgrade need a migration that sets the configured id.
`edc.participant.context.id` is the recommended explicit setting.

## Virtual mode: several participants

`core/common/participant-context-connector-core` (`ConnectorParticipantContextExtension`, in
both BOMs) provides the pieces the virtual control plane relies on:

- `ParticipantContextIdentityResolverImpl` — participant id = `ParticipantContext.identity`
  (DR `2025-10-29-participant-identifiers`);
- `ParticipantWebhookResolverImpl` — formats the profile's callback URL with the context id;
- `ParticipantProfileServiceImpl` — which dataspace profiles a participant uses (per-participant
  key `edc.dataspace.profiles`, CSV; `edc.dataspace.enable.profiles.all` lets every participant
  use every profile).

`controlplane-virtual-base-bom` then swaps in:

| Concern | Classic | Virtual |
|---|---|---|
| DSP endpoints | `/<protocol path>/2025-1/...` (`dsp`) | `/<protocol path>/{participantContextId}/{profileId}/...` (`dsp-virtual`); `/{participantContextId}/.well-known/dspace-version` |
| callback address | `edc.dsp.callback.address` | with `web.http.protocol.virtual=true` and no callback address, `http://host:port/path/%s`, filled with the context id (`DspApiBaseConfigurationExtension`) |
| Management API | `management-api` v3/v4 | `management-api-v5` (`/v5beta/participants/{participantContextId}/...`) with scope + ownership checks — see [Management API](management-api.md) |
| state machines | polling managers | task executors (`control-plane-*-task-executor`, optional NATS) |
| policy | — | `cel-core` |

DR `2026-05-11-multi-profile-virtual-connector`: one virtual runtime serves several dataspace
profiles; the profile `name` is both the DSP path segment and the protocol string (default
`http-dsp-profile-2025-1`); controllers reject a profile the participant is not associated
with. Profiles are registered with `edc.dataspace.profiles.<alias>.{name, protocol.version,
protocol.binding, protocol.namespace, jsonld.context.urls}`
(`data-protocols/dsp/dsp-virtual/dsp-http-core-virtual/.../DataspaceProfileConfigurationExtension.java`)
and associated through `PUT /v5beta/participants/{id}/profiles`.

## What is per participant in 0.18.0

| Concern | Per participant? | How |
|---|---|---|
| assets, policies, contract definitions, negotiations, agreements, transfers, data planes, EDR entries | yes | `participantContextId` on the entity; v5 filters by it |
| participant id on the wire | yes | `ParticipantContext.identity` |
| own DID (DCP) | yes | `DidConfigProvider` reads `edc.participant.id`, `edc.participant.did`, `edc.iam.issuer.id` from `ParticipantContextConfig` |
| STS client | yes | `StsRemoteClientExtension` reads `edc.iam.sts.oauth.token.url`, `.client.id`, `.client.secret.alias` from `ParticipantContextConfig` |
| secrets | where the vault supports it | `Vault` partition overloads default to the unpartitioned methods; `HashicorpVault` (`extensions/common/vault/vault-hashicorp/`) keeps one client per partition from the private entry `edc.vault.hashicorp.config`, falling back to the default vault if `edc.vault.hashicorp.allow-fallback` (default true). Callers passing the context id: `VaultPrivateKeyResolver`, `VaultDataAddressStore`, `RemoteSecureTokenService` |
| DSP profiles | yes | `edc.dataspace.profiles` per participant |
| DCP scopes | not verified | `DcpScope` has no participant field in the source read |
| trusted issuers, policy functions, transformers | no | runtime-wide registries |

The in-memory `Vault` default from `BootServicesExtension` is constructed with the single
participant supplier; how it behaves with several partitions was not verified.

## IdentityHub per participant

IdentityHub (same version) is multi-participant by construction. Creating a participant
context (`IdentityHub: core/identity-hub-participants/.../IdentityHubParticipantContextServiceImpl.java`)
from a `ParticipantManifest` (id, DID, keys, service endpoints, active flag, scopes):

- generates an API key `base64(id).base64(random)` and stores it in the vault partition of
  that context;
- provisions an STS account (client id = DID) and returns `clientId` / `clientSecret`
  (`CreateParticipantContextResponse`);
- on the `ParticipantContextCreated` event, creates the DID document and key pairs and, if
  active, publishes the DID (`ParticipantContextEventCoordinator`).

Per-participant endpoints are under `/v1beta/participants/{participantContextId}/...`
(Identity API) and `/v1/participants/{participantContextId}/...` (DCP credential service).
See [Identity and trust](identity-and-trust.md#identityhub).

## The Virtual-Connector project

`eclipse-edc/Virtual-Connector` describes itself as "EDC core components and services for a
virtualized control plane" and builds against `0.18.0-SNAPSHOT`. Its history shows the
management v5 API, the participant-context APIs, the virtual DSP implementation, the task
subsystem, NATS and the virtual BOMs moving upstream into `Connector`; at the revision read
(`9d9afa7`, "remove virtual boms") it contains two modules, a banner extension and a
task-store poll executor. Its `docs/access_control.md` still describes the role- and
`participant_context_id`-based scheme that DR `2026-06-06` replaced.

## What ds adds on top

ds runs the classic single-participant control plane: one EDC runtime per participant, with
`edc.participant.id` set to the participant's DID
([edc-connector](../../services/edc-connector.md#the-settings-that-matter)).
`edc.participant.context.id` is set neither in `services/connector/config/*.properties` nor
in the Helm chart, so the context id falls back to the DID.
