# edc-connector

`services/edc-connector/` contains **no source code**. It is a Gradle Shadow build that
assembles an Eclipse Dataspace Components runtime — EDC `0.16.0`, DCP-enabled — out of
upstream EDC BOMs plus this repository's [`edc-extensions`](edc-extensions.md), and a
two-stage Dockerfile that packages the resulting `connector.jar` into a JRE image.

One image, deployed once per participant, each with its own configuration file, database and
DID. Everything it serves comes from either upstream EDC or `edc-extensions`; this unit
contributes the assembly, the packaging and one build-time assertion.

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
| `controlplane-dcp-bom` | the whole control plane: DSP 2025-1 HTTP APIs, Management API v3 and v4beta, contract / transfer / policy state machines, DCP identity, the STS remote client, VC verification, the policy monitor |
| `dataplane-base-bom` | data-plane core, HTTP data source, signalling API and client, data-plane selector and self-registration |
| `identity-did-web` | `did:web` resolution |
| `control-plane-sql`, `data-plane-store-sql`, `edr-index-sql`, `policy-monitor-store-sql`, `sql-lease-core`, `sql-pool-apache-commons`, `transaction-local` | PostgreSQL persistence for every store — without the policy-monitor store a restart forgets every watched transfer |
| `configuration-filesystem` | the `edc.fs.config` properties reader |
| `:edc-extensions` | this platform's constraint functions, pending guard, resume route, event publisher, vault seeder and the forked policy transformer |

That resolves to roughly 190 EDC modules and 160 registered service extensions.

## The API contexts

The runtime binds a Jetty connector only for contexts something registers. Four are live.

| Context | Path | Provider | Consumer | Authentication |
|---|---|---|---|---|
| `default` | `/api` | 19191 | 29191 | **none** — health and liveness probes |
| `control` | `/control` | 19192 | 29192 | **none** — data-plane signalling, in-cluster only |
| `management` | `/management` | 19193 | 29193 | `X-Api-Key` |
| `protocol` | `/protocol` | 19194 | 29194 | DSP/DCP self-issued token; `/.well-known/dspace-version` is open |

**Only `protocol` is ever public.** Management creates and deletes assets, policies and
transfers; control drives the data plane. Both are ClusterIP plus NetworkPolicy in Kubernetes
and unpublished in compose, and the exposure is denied twice — at routing and at the network
layer.

The Management API surface is upstream EDC's v3 and v4beta CRUD over assets, policy
definitions, contract definitions, negotiations, transfer processes, agreements, EDRs and data
planes — plus exactly one route this repository adds:
`POST /management/dataspaces/negotiations/{id}/resume`.

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

The environment mapping lower-cases and turns `_` into `.`, so `WEB_HTTP_MANAGEMENT_AUTH_KEY`
becomes `web.http.management.auth.key`.

!!! warning "No interpolation in properties files"
    `FsConfigurationExtension` does a plain `Properties.load()`. A `${EDC_API_KEY}` written
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
| `edc.dsp.callback.address` | `http://172.17.0.1:19194/protocol` | the address counterparties call back on |
| `web.http.<context>.port` / `.path` | see the table above | context binding |
| `web.http.management.auth.type` | `tokenbased` | the only context with an auth filter |
| `web.http.management.auth.key` | *(from `EDC_API_KEY`)* | **secret** — the Management API key |
| `edc.iam.sts.oauth.token.url` | `…/sts/<did>/token` on the identity registry | where this EDC gets its DCP token |
| `edc.iam.sts.oauth.client.id` / `.client.secret.alias` | the DID / a vault alias | STS credentials |
| `edc.iam.trusted-issuer.0.id` | `did:web:trust-anchor.dataspaces.localhost` | whose credentials are believed |
| `edc.iam.dcp.scopes.membership.*` | `MembershipCredential:read` | which credential is requested in a presentation |
| `edc.iam.did.web.use.https` | `false` in dev, **`true` in production** | DID documents carry the keys every trust decision rests on |
| `edc.vault.fs.file` | `/config/<role>-vault.properties` | the filesystem vault seed |
| `edc.transfer.proxy.token.signer/verifier.publickey.alias` | `participant-private-key` | the EDR signing key |
| `edc.datasource.default.url` / `.user` / `.password` | `jdbc:postgresql://…/edc_rec` | one database per participant |
| `edc.sql.schema.autocreate` | `true` | see below |
| `ds.connector.internal.url` | `http://172.17.0.1:30001` | the ds-connector this runtime asks |

### Supplied from the environment

| Variable | Becomes | Why environment |
|---|---|---|
| `WEB_HTTP_MANAGEMENT_AUTH_KEY` | `web.http.management.auth.key` | secret |
| `DS_CONNECTOR_INTERNAL_TOKEN_URL` / `_CLIENT_ID` / `_CLIENT_SECRET` | `ds.connector.internal.*` | secret; empty is fatal at boot |
| `EDC_DATASOURCE_DEFAULT_USER` / `_PASSWORD` | database credentials | secret |
| `DS_DEMO_IDENTITY_ENABLED` | `ds.demo.identity.enabled` | dev only — see [edc-extensions](edc-extensions.md) |
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
| in | ds-connector | the Management API, with `X-Api-Key` |

## Build

Two Dockerfiles, both with the repository root as build context.

| File | Produces |
|---|---|
| `Dockerfile.base` | `ds-edc-base:0.16.0` — a `gradle:8.12-jdk21` image with the resolved dependency cache baked in, so a normal build does not re-resolve ~190 modules |
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
