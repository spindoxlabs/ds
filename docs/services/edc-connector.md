# edc-connector

`services/edc-connector/` contains **no source code**. It is a Gradle Shadow build that
assembles an Eclipse Dataspace Components runtime — EDC `0.18.0`, DCP-enabled — out of
upstream EDC BOMs plus this repository's [`edc-extensions`](edc-extensions.md), and a
two-stage Dockerfile that packages the resulting `connector.jar` into a JRE image.

One image, deployed once per participant, each with its own configuration file, database and
DID. Everything it serves comes from either upstream EDC or `edc-extensions`; this unit
contributes the assembly, the packaging and one build-time assertion.

How the upstream runtime works inside is described in [EDC internals](../edc/index.md).

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Data Exchange](../blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Control and Data Plane](../blueprints/dssc/control-and-data-plane.md) |
| Rules it enforces | [Rulebook · Data exchange](../rulebook/data-exchange.md) — the accepted protocols and the version pin |

This is the **protocol engine**: it speaks the Dataspace Protocol to other participants, runs
the contract-negotiation and transfer state machines, and signs the Endpoint Data References a
consumer pulls with. What it may do is decided by [`ds-connector`](connector.md).

## What the runtime is made of

| BOM / module | Contributes |
|---|---|
| `controlplane-dcp-bom` | the whole control plane: DSP 2025-1 HTTP APIs, Management API v3 (deprecated) and v4, contract / transfer / policy state machines, DCP identity, the STS remote client, VC verification, the policy monitor |
| `dataplane-base-bom` | data-plane core, HTTP data source, signalling API and client, data-plane selector and self-registration |
| `identity-did-web` | `did:web` resolution |
| `control-plane-sql`, `data-plane-store-sql`, `edr-index-sql`, `policy-monitor-store-sql`, `sql-lease-core`, `sql-pool-apache-commons`, `transaction-local` | PostgreSQL persistence for every store — without the policy-monitor store a restart forgets every watched transfer |
| `configuration-filesystem` | the `edc.fs.config` properties reader |
| management API v5 | `asset-api-v5`, `policy-definition-api-v5`, `contract-definition-api-v5`, `catalog-api-v5`, `contract-negotiation-api-v5`, `contract-agreement-api-v5`, `transfer-process-api-v5`, `participant-context-api-v5`, `management-api-schema-validator`, `management-api-oauth2-authentication`, `management-api-authorization` — added one by one; the DCP BOM carries none of them |
| `:edc-extensions` | this platform's constraint functions, pending guard, resume route, event publisher, vault seeder and the forked policy transformer |

The DCP BOM's **classic (v3/v4) management controllers are excluded** — `asset-api` … `transfer-process-api`, `edr-cache-api`, `data-plane-selector-api`, `federated-catalog-api`. None of them checks a scope or ownership, so behind the OAuth2 filters they would admit any token naming a participant context.

That resolves to roughly 190 EDC modules and 160 registered service extensions.

## The API contexts

The runtime binds a Jetty connector only for contexts something registers. Four are live.

| Context | Path | Provider | Consumer | Authentication |
|---|---|---|---|---|
| `default` | `/api` | 19191 | 29191 | **none** — health and liveness probes |
| `control` | `/control` | 19192 | 29192 | `x-api-key` — data-plane signalling, in-cluster only |
| `management` | `/management` | 19193 | 29193 | OAuth2 bearer token: `sub` = this participant context, `scope` in EDC's grammar |
| `protocol` | `/protocol` | 19194 | 29194 | DSP/DCP self-issued token; `/.well-known/dspace-version` is open |

**Only `protocol` is ever public.** Management creates and deletes assets, policies and
transfers; control drives the data plane. Neither is routed by an Ingress, control is not even
a Service port, and both are unpublished in compose — so the exposure is denied at routing and
again at the network layer.

**For management, that isolation is the control, not a second line.** EDC never checks a
management token's audience. One client per organisation is shared by its connector and its
batch jobs, so whoever holds that client's token can administer the organisation's contracts
on any network that reaches the port. Compose publishes no `x9193` port (asserted by
`services/connector/tests/test_management_port_isolation.py`, and live by `ds-e2e --flow
organisation-token`). The connector reaches the port on the project network as
`edc-<participant>:<port>`. The chart keeps it ClusterIP-only, behind the NetworkPolicy. See
[ADR-0014](../decisions/ADR-0014-management-api-v5-and-the-organisation-actor.md).

**Control is authenticated too.** Until `web.http.control.auth.type=tokenbased` was set,
`GET /control/v1/dataplanes` returned 200 with the full data-plane registry to any container on
the network — measured, not inferred. The filter is free here because the data-plane client is
**embedded**: the control plane signals its own data plane in-process, so its own calls never
cross the port. The key is `WEB_HTTP_CONTROL_AUTH_KEY`, its own secret rather than the
Management API's.

Splitting the data plane into a separate runtime would change that. The only
`ControlClientAuthenticationProvider` packaged here is the no-op default from
`CoreDefaultServicesExtension`, so signalling would 401 the moment it became a real HTTP call.

**There is no `public` or `version` context.** Both used to be configured — in every
participant properties file, in compose port mappings, in the chart's container, Service and
NetworkPolicy ports, and `/public` was an Ingress path — and no packaged module registers a
resource on either. `ApiContext` declares `MANAGEMENT`, `CONTROL` and `PROTOCOL` only; no
data-plane public API is on the classpath; the management Version API registers on the default
context. `RuntimeContractTest` fails if either is configured again.

The Management API surface is upstream EDC's **v5** (`/management/v5beta/participants/{participantContextId}/…`
at 0.18.0) over assets, policy definitions, contract definitions, the catalogue, negotiations,
agreements and transfer processes — plus exactly one route this repository adds:
`POST /management/dataspaces/negotiations/{id}/resume`, which requires
`management-api:negotiations:write` and EDC's ownership check for this runtime's participant
context. There is no v3 or v4 route, and no EDR route (EDC 0.18.0 has none in v5).

**Who may call it.** `management-api-oauth2-authentication` validates the bearer token against
the realm's JWKS, its issuer, `nbf` and `exp` — **never `aud`** — and requires `sub` to name a
participant context (`management-api:admin` skips that; ds grants it to nobody).
`management-api-authorization` then enforces each route's `@RequiredScope` and the ownership
check. The token comes from the organisation's Keycloak client — see
[keycloak](keycloak.md#organisation-clients). There is no `web.http.management.auth.type`: beside
these filters it would demand an `x-api-key` on every call as well.

The protocol context advertises a single DSP version:

```
GET /protocol/.well-known/dspace-version
{"protocolVersions":[{"version":"2025-1","path":"/2025-1","binding":"HTTPS"}]}
```

## Configuration

### How settings resolve

`BaseRuntime` builds its config from three sources, in increasing precedence:

```
properties file  <  environment  <  -D system properties
```

The environment mapping lower-cases and turns `_` into `.`, so `WEB_HTTP_CONTROL_AUTH_KEY`
becomes `web.http.control.auth.key`.

!!! warning "No interpolation in properties files"
    `FsConfigurationExtension` does a plain `Properties.load()`. A `${EDC_CONTROL_API_KEY}` written
    into a `.properties` file is stored as that literal string. **Every secret-bearing setting
    must come from the environment.** The ds extension defends against the mistake by treating
    any value containing `${` as absent, which turns it into a startup failure.

### The settings that matter

Dev values come from `services/connector/config/{provider,consumer}.properties`; the Helm
chart renders its own equivalent. The two roles are structurally identical, with ports
differing by +10000 and a different DID, vault, database and connector URL.

| Setting | Provider value | Meaning |
|---|---|---|
| `edc.participant.id` / `edc.iam.issuer.id` | `did:web:rec.dataspaces.localhost` | this participant's DID |
| `edc.participant.context.id` | the same DID | the one participant context of this classic runtime — the `sub` its organisation client carries. The value the runtime already stamped on every stored entity (it was the fallback), so it needs no migration |
| `edc.iam.oauth2.issuer` / `edc.iam.oauth2.jwks.url` | the realm issuer / its JWKS on the host gateway | what the management API trusts. Under Helm, `global.keycloak.issuerUrl` (required) and `jwksUrl` |
| `edc.dataspace.enable.profiles.all` | `true` | v5 resolves a request's dataspace profile per participant (`ParticipantProfileService`) and answers `400` "No profile … for participant" otherwise. The classic runtime registers exactly one, DSP `2025-1`, so enabling all of them enables that one. Listing it explicitly instead would restate the protocol pin |
| `edc.dsp.callback.address` | `http://172.17.0.1:19194/protocol` | the address counterparties call back on |
| `web.http.<context>.port` / `.path` | see the table above | context binding |
| `web.http.control.auth.type` | `tokenbased` | the one context with a key filter — `auth.key` alone installs none. Not set on `management`, which is OAuth2 |
| `web.http.control.auth.key` | *(from `EDC_CONTROL_API_KEY`)* | **secret** — the control API key. Its own value; nothing outside the runtime holds it |
| `edc.iam.sts.oauth.token.url` | `…/sts/<did>/token` on the identity registry | where this EDC gets its DCP token |
| `edc.iam.sts.oauth.client.id` / `.client.secret.alias` | the DID / a vault alias | STS credentials |
| `edc.iam.trusted-issuer.0.id` | `did:web:trust-anchor.dataspaces.localhost` | whose credentials are believed |
| `edc.iam.dcp.scopes.membership.*` | `MembershipCredential:read` | which credential is requested in a presentation |
| `edc.iam.did.web.use.https` | `false` in dev, **`true` in production** | DID documents carry the keys every trust decision rests on |
| `ds.vault.seed.file` | `/config/<role>-vault.properties` | the vault seed. It also holds `ds-connector-callback-key`, the header value EDC sends with the EDR callback (under Helm, `secrets.edcCallbackKey`). **The only thing that puts anything in the vault** — the sole `Vault` on the classpath is EDC's in-memory default. Was `edc.vault.fs.file`, the key EDC's own `vault-filesystem` module reads; still honoured, with a deprecation warning |
| `edc.transfer.proxy.token.signer/verifier.publickey.alias` | `participant-private-key` | the EDR signing key |
| `edc.datasource.default.url` / `.user` / `.password` | `jdbc:postgresql://…/edc_rec` | one database per participant |
| `edc.sql.schema.autocreate` | `true` | see below |
| `ds.connector.internal.url` | `http://172.17.0.1:30001` | the ds-connector this runtime asks |
| `ds.edr.endpoint.public.baseurl` | `http://172.17.0.1:30002` | **the dataset API**, not this connector — the origin an asset's own `base_url` is rewritten to in the EDR. Consumer-pull traffic goes straight to the data plane; EDC never proxies it. Under Helm it defaults to unset, so the asset's `base_url` reaches the consumer verbatim |

**Four settings that used to be here are gone**, each read by no class in `connector.jar`:
`edc.dataplane.api.public.baseurl`, `edc.credential.service.url`, `edc.vault.hashicorp.enabled`
and `edc.api.key`. EDC ignores an unknown key silently, so they looked like configuration and
were not — a counterparty finds this participant's credential service through its DID document. `RuntimeContractTest` fails if a
setting with no reader is added back.

### Supplied from the environment

| Variable | Becomes | Why environment |
|---|---|---|
| `WEB_HTTP_CONTROL_AUTH_KEY` | `web.http.control.auth.key` | secret |
| `DS_CONNECTOR_INTERNAL_TOKEN_URL` / `_CLIENT_ID` / `_CLIENT_SECRET` | `ds.connector.internal.*` | secret; empty is fatal at boot |
| `EDC_DATASOURCE_DEFAULT_USER` / `_PASSWORD` | database credentials | secret |
| `DATASPACES_ODRL_NAMESPACE` | `dataspaces.odrl.namespace` | must match the connector's ODRL profile — see [edc-extensions](edc-extensions.md) |
| `JAVA_OPTS` | JVM heap | image default `-Xms256m -Xmx512m` |

### Schema creation

`edc.sql.schema.autocreate=true` means the runtime creates its own tables at first boot from
DDL resources inside the JAR. **Flyway is not on the classpath**, so "run migrations
out-of-band" means applying those `*-schema.sql` resources yourself. The deployment keeps
autocreate on and instead gives each EDC a least-privilege role that owns only its own
database, which removes the real risk — DDL as a superuser — while keeping the connector
self-migrating.

## Persistence

Ten tables in a per-participant database (`edc_rec`, `edc_third_party`), all created by the
runtime: `edc_asset`, `edc_policydefinitions`, `edc_contract_definitions`,
`edc_contract_negotiation`, `edc_contract_agreement`, `edc_transfer_process`,
`edc_data_plane`, `edc_edr_entry`, `edc_policy_monitor`, `edc_lease`.

The databases themselves are created outside the connector — by a one-shot container in
compose, by CloudNativePG in Kubernetes.

## Who it talks to

| Direction | Counterpart | For |
|---|---|---|
| out | [ds-connector](connector.md) `/internal/*`, `/webhooks/*` | policy decisions and lifecycle events, as `svc-edc` |
| out | [identity-registry](identity-registry.md) | STS tokens, DCP presentation queries, `did:web` resolution |
| out | Keycloak | the `client_credentials` token for the connector calls |
| out | its own PostgreSQL database | every store |
| both | **peer EDCs** | DSP over `/protocol/2025-1` |
| in | ds-connector | the Management API v5, with its organisation client's token |

## Known behaviour: a half-registered runtime after a restart

Right after a container restart, the runtime can answer for a while before every controller
is registered. A management call then gets `405` or `404` on a route that exists (for example
`POST …/assets/request`), and `/api/check/health` can get `404`. It clears without
intervention, sometimes after tens of seconds, and once only after a second restart. The
readiness gates in `task e2e:wait-ready` and `task e2e:prepare` treat `000`, `404` and `405` as
*not ready*. They probe a v5 route rather than the health endpoint, through `docker exec` when
the EDC is a container, because the management port is not on the host.

## Build

Two Dockerfiles, both with the repository root as build context.

| File | Produces |
|---|---|
| `Dockerfile.base` | `ds-edc-base:0.18.0` — a `gradle:8.12-jdk21` image with the resolved dependency cache baked in, so a normal build does not re-resolve ~190 modules |
| `Dockerfile` | builder stage runs `gradle :edc-connector:shadowJar`; runtime stage is `eclipse-temurin:21-jre-alpine` with uid/gid 10001 and `connector.jar` |

`shadowJar` merges service files (so this repo's extensions register alongside upstream's),
excludes duplicates first-wins, and is finalised by `verifyForkedTransformer` — a task that
opens the JAR and fails the build unless the packaged `JsonObjectFromPolicyTransformer` is the
forked copy.

| Task | Effect |
|---|---|
| `task edc:base` / `edc:ensure-base` | build the dependency-cache image, if missing |
| `task edc:build` | build `connector.jar` on the host |
| `task edc:restart` | rebuild the JAR and the image, recreate both EDC containers, wait for health |
| `task edc-rec:run` / `edc-third-party:run` | run the JAR on the host against the dev properties |
| `task edc-rec:watch` / `edc-third-party:watch` | the same JVM under a supervision loop that restarts on JAR change |

Changing the EDC version means editing `edcVersion` in `build.gradle.kts` **and** the four
other places the tag is written: both Dockerfiles and two Taskfile entries.
