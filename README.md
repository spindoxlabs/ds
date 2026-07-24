# Dataspaces

A DSSC-aligned dataspace implementation for energy communities, built on top of Eclipse Dataspace Connector.

The project delivers the full consumer-pull data exchange flow: catalogue discovery, contract negotiation, EDR-gated data transfer, consent enforcement, and provenance tracking — all aligned to the DSSC Blueprint Building Blocks.

---

## What it provides

Participants in the dataspace can publish datasets through a governed catalogue and allow other participants to negotiate contracts, obtain Endpoint Data References, and query data with row-level consent filtering applied at query time.

The stack covers the following DSSC Blueprint building blocks:

- **BB02** — Participant identities as `did:web:` URIs with `JsonWebKey2020` verification methods
- **BB05** — ODRL policies derived from `governance.yaml` with access-level, purpose, consent, and obligation constraints
- **BB06** — EDC-based data exchange with EDR token issuance and HTTP data plane proxy
- **BB07** — W3C PROV-O provenance logging via a JSON-LD REST API
- **BB08** — DCAT-AP 3.0 catalogue with `application/ld+json` responses
- **BB09** — Consent portal for per-subject data usage consent, with revocation linked to active transfer processes
- **DCP** — Dataspace Credential Protocol identity verification using Verifiable Credentials

---

## Repository layout

```
dataspaces/
├── docker-compose.yml          shared infra — caddy, postgres, identity-registry, keycloak
├── docker-compose.provider.yml provider participant stack
├── docker-compose.consumer.yml consumer participant stack
├── Taskfile.yml                root orchestration
├── build.gradle.kts            Gradle root (EDC subprojects)
├── settings.gradle.kts
├── services/
│   ├── caddy/                  reverse proxy config + DID document routing
│   ├── connector/              port 30001/31001 — EDC orchestrator (Python/FastAPI)
│   ├── provenance/             port 30000/31000 — PROV-O REST API (Python/FastAPI)
│   ├── portal/                 port 30004 — web frontend (SvelteKit)
│   ├── governance/             shared Python library — GovernanceRuleV2 + ODRL mapper
│   ├── identity-registry/      port 30005 — DID lifecycle, STS, credential service, participant registry
│   ├── federated-catalog/      port 30003 — DCAT-AP catalog crawler (Python/FastAPI)
│   ├── dataset-api-mock/       port 30002 — mock dataset API for dev
│   ├── dataset-api-fiware-adapter/  FIWARE NGSI-LD adapter
│   ├── edc-connector/          Gradle — DCP-enabled EDC connector fat JAR (v0.16.0)
│   ├── edc-extensions/         Java — custom ODRL constraint functions for EDC
│   └── keycloak/               OIDC realm import for dev
├── data/                       runtime data (gitignored) — caddy PKI, gradle cache
└── docs/                       architecture docs, DSSC blueprint reference
```

---

## Quick start

### Prerequisites

- Docker with Compose v2
- [Task](https://taskfile.dev) (v3+)
- [uv](https://docs.astral.sh/uv/) (for local Python service overrides)
- Node.js (for the portal)

### Start in local development mode

Brings the container stack up, then replaces most services with hot-reload host
processes in a tmux session named `ds`. Fast to iterate on; it does **not**
exercise the service Dockerfiles or the compose `environment:` blocks.

Note: requires `tmux` installed (eg. `apt install tmux`)

```bash
task dev:restart          # stop + start, then attach to the tmux session
task dev:stop             # stop everything, including the watch loops
```

### Start the full stack (everything in containers)

The mode that validates a change to a Dockerfile, a compose environment block or
a dependency — nothing runs on the host.

```bash
task docker:restart              # stop + rebuild images + start
task docker:restart BUILD=false  # skip the rebuild (fast; only when source is unchanged)
task docker:stop
```

`task start` alone starts the stack without stopping anything first or
rebuilding images.

```bash
task start
```

This brings up, in order:

1. **Shared infrastructure** — postgres, caddy, identity-registry, keycloak (+ keycloak-sync for scopes/clients)
2. **Identity bootstrap** — trust anchor + provider/consumer participant registration
3. **Provider stack** — EDC provider, ds-connector, ds-provenance, dataset-api, federated-catalog
4. **Consumer stack** — EDC consumer, ds-connector, ds-provenance

Or step by step:

```bash
task infra:start          # shared infra (postgres, caddy, identity-registry, keycloak)
task identity:bootstrap   # trust anchor + participant DIDs
task provider:start       # provider participant stack
task consumer:start       # consumer participant stack
```

### Portal (local dev with hot-reload)

```bash
task provider:portal:run  # SvelteKit dev server on http://localhost:30004
```

### Stop everything

```bash
task stop
```

### Verify the stack

After services are up, the following should respond:

- `http://localhost:30001/health` (provider connector)
- `http://localhost:31001/health` (consumer connector)
- `http://localhost:30005/health` (identity-registry)
- `http://localhost:30005/dids/did:web:provider.dataspaces.localhost/did.json` (DID document)

---

## Services

### identity-registry (`services/identity-registry`)

Centralized trust anchor service (DSSC BB02). Manages DID lifecycle, STS token issuance (ES256 SI JWTs), DCP credential service, participant registry, and StatusList2021. DID private keys never leave this service — they are Fernet-encrypted at rest.

### ds-connector (`services/connector`)

The central orchestration layer. Wraps both an EDC provider and consumer connector instance, exposes a clean REST API for governance sync, consumer data flows, consent management, and participant registry lookups. Uses PostgreSQL via async SQLAlchemy + Alembic.

### ds-provenance (`services/provenance`)

A W3C PROV-O compatible REST API that logs catalogue publication, contract negotiation, data transfer, and obligation fulfilment events as linked-data graph nodes. Uses a relational database with BFS lineage traversal — no triple stores.

### ds-portal (`services/portal`)

A SvelteKit web application covering the full portal surface: catalogue browser, consumer negotiation wizard, provider governance management, consent portal for data subjects, and provenance lineage viewer.

### ds-federated-catalog (`services/federated-catalog`)

A DCAT-AP catalog crawler. Periodically queries participant connectors and builds an aggregated catalog. Backed by the connector's participant registry.

### edc-extensions (`services/edc-extensions`)

Java extensions for the EDC policy engine. Registers `AtomicConstraintFunction` implementations for the profile-namespaced ODRL constraints (e.g. `dsp-policy:Membership`, `dsp-policy:ConsentStatus`).

### edc-connector (`services/edc-connector`)

Gradle project that assembles a fat JAR combining EDC v0.16.0 modules with DCP support. Built via a versioned base image (`ds-edc-base:0.16.0`) that pre-caches all Maven dependencies.

---

## How services interact

```
Portal (30004) ──→ ds-connector (30001/31001) ──→ EDC Provider/Consumer
                                               ──→ ds-provenance (30000/31000)
                                               ──→ Federated Catalog (30003)

EDC Provider ←──DSP──→ EDC Consumer
  ├──→ identity-registry (30005)   STS token issuance (/sts/{did}/token)
  ├──→ identity-registry (30005)   VP queries (/credentials/{did}/presentations/query)
  └──→ ds-connector /internal/*    ODRL constraint evaluation

identity-registry (30005)
  ├── DID documents      Caddy rewrites /.well-known/did.json → /dids/{did}/did.json
  ├── STS tokens         POST /sts/{did}/token (ES256 SI JWTs)
  ├── Credential service POST /credentials/{did}/presentations/query (DCP VP queries)
  ├── Participant registry GET /admin/participants, GET /admin/participants/check?did=&scope=
  └── StatusList2021     GET /status/{list_id}

Federated Catalog (30003) ──→ identity-registry /participants (provider discovery)
ds-connector ──→ identity-registry /participants (HttpParticipantRegistry with TTL cache)

dataset-api (30002, external) ──→ ds-connector /internal/*  agreement + consent checks
```

---

## Compose topology

Three compose files form the full stack:

| File | Services | Purpose |
|------|----------|---------|
| `docker-compose.yml` | caddy, postgres, identity-registry, keycloak | Shared infrastructure |
| `docker-compose.provider.yml` | edc-provider, ds-connector-provider, ds-provenance-provider, dataset-api-provider, ds-federated-catalog-provider | Provider participant |
| `docker-compose.consumer.yml` | edc-consumer, ds-connector-consumer, ds-provenance-consumer | Consumer participant |

The portal runs in the provider compose. For local dev with hot-reload: `task provider:portal:run`.

All containers share the `dataspaces` bridge network.

## Port scheme

| Port | Service |
|------|---------|
| 30000 | ds-provenance (provider) |
| 30001 | ds-connector (provider) |
| 30002 | dataset-api (provider) |
| 30003 | federated-catalog (provider) |
| 30004 | portal (run locally) |
| 30005 | identity-registry (shared infra) |
| 31000 | ds-provenance (consumer) |
| 31001 | ds-connector (consumer) |
| 35432 | PostgreSQL |
| 9080 | Keycloak |
| 9000 | Caddy consumer gateway |
| 9010 | Caddy provider gateway |
| 19xxx | EDC provider (management, protocol, public, control) |
| 29xxx | EDC consumer (management, protocol, public, control) |
| 30900+ | debugpy ports |

---

## Local dev overrides

Any service can be run locally (with hot-reload) instead of in Docker. Stop the container first, then run the service with `task`:

```bash
# Example: run provider connector locally
task provider:connector:run

# Or with debugpy attached
task provider:connector:debug
```

Available overrides: `task identity-registry:run`, `task provider:connector:run`, `task provider:provenance:run`, `task provider:dataset-api:run`, `task provider:federated-catalog:run`, `task consumer:connector:run`, `task consumer:provenance:run`.

---

## Participant identities

Each participant is identified by a `did:web:` URI:

- Provider: `did:web:provider.dataspaces.localhost`
- Consumer: `did:web:consumer.dataspaces.localhost`
- Trust anchor: `did:web:trust-anchor.dataspaces.localhost`

DID documents are served dynamically by identity-registry. Caddy rewrites `/.well-known/did.json` requests to the identity-registry API.

DID private keys are generated and stored inside identity-registry, encrypted at rest with Fernet. The `ir-cli` tool (inside the identity-registry container) handles bootstrap and participant registration — see `task identity:bootstrap`.

---

## Governance and ODRL policies

Datasets are described in `services/connector/governance/governance.yaml`. The pipeline:

```
governance.yaml → GovernanceResolver → GovernanceRuleV2 → GovernanceMapper
  → ODRL Offer + EDC Asset + EDC PolicyDefinition + EDC ContractDefinition
  → POST /provider/sync pushes to EDC Management API
  → EDC serves to consumers via DSP
  → edc-extensions evaluate constraints at negotiation time
```

Access levels map to ODRL as follows:

- `open` — no constraints; `downloadURL` included in DCAT distribution
- `internal` / `restricted` — constraints driven by the `access_requirements` field; `partner` adds a profile-namespaced `Membership` constraint (e.g. `dsp-policy:Membership`)
- `secret` — not exposed to EDC or the catalogue

When `user_filter_column` is set on a dataset, a profile-namespaced `ConsentStatus` constraint (e.g. `dsp-policy:ConsentStatus eq "active"`) is added to the ODRL offer and consent-based row filtering is applied at query time.

---

## Data exchange flow

```
Consumer negotiates via ds-connector
  POST /consumer/negotiate → negotiation_id
  GET  /consumer/negotiations/{id} → FINALIZED
  POST /consumer/transfer → transfer_id
  GET  /consumer/transfers/{id} → STARTED
  GET  /consumer/edr/{id} → EDR (endpoint + token)

Consumer queries dataset-api
  POST /query  (Edc-Contract-Agreement-Id, Edc-Bpn headers)
  → agreement check via ds-connector /internal/agreements/{id}/status
  → consent row-filter via ds-connector /internal/consent/check
  → SQL executed with IN(subject_ids) predicate
```

---

## Compliance evidence

```bash
task compliance:validate
task compliance:test
task compliance:e2e:smoke   # requires a running stack
```

See `docs/dssc-blueprint-docs/` for the DSSC blueprint reference material.

---

## Useful task commands

| Command | Description |
|---------|-------------|
| `task start` | Start everything |
| `task stop` | Stop everything |
| `task status` | Show all running containers |
| `task provider:logs` | Follow provider logs |
| `task consumer:logs` | Follow consumer logs |
| `task reset-demo-state` | Clear runtime data (requests, consents, agreements, transfers, provenance) |
| `task edc:base` | Build EDC base image (once per version bump) |

Run `task --list` for all available commands.

---

## License

Copyright © 2025 Spindox Labs

Licensed under the Apache License, Version 2.0.
