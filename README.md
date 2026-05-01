# Dataspaces

A DSSC-aligned dataspace implementation for energy communities, built on top of Eclipse Dataspace Connector and the CELINE open data platform.

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
├── docker-compose.yml          shared infra — caddy, postgres (port 35432)
├── Taskfile.yml                root orchestration
├── build.gradle.kts            Gradle root (EDC subprojects)
├── settings.gradle.kts
├── services/
│   ├── caddy/                  reverse proxy config + DID document hosting
│   ├── connector/              port 30001 — EDC orchestrator (Python/FastAPI)
│   ├── provenance/             port 30000 — PROV-O REST API (Python/FastAPI)
│   ├── portal/                 port 30004 — web frontend (SvelteKit)
│   ├── governance/             shared Python library — GovernanceRuleV2 + ODRL mapper
│   ├── sts/                    ports 38080/38081 — Security Token Service (Python/FastAPI)
│   ├── vc-wallet/              ports 38082/38083 — Credential Service (Python/FastAPI)
│   ├── federated-catalog/      port 30003 — DCAT-AP catalog crawler (Python/FastAPI)
│   ├── edc-connector/          Gradle — DCP-enabled EDC connector fat JAR (v0.16.0)
│   └── edc-extensions/         Java — custom ODRL constraint functions for EDC
├── data/                       runtime data (gitignored) — caddy PKI, keys, credentials
├── scripts/                    key generation, VC issuance
└── docs/                       architecture docs, DSSC blueprint reference
```

Each service under `services/` has:
- `docker-compose.yml` — service containers (references shared infra network)
- `Taskfile.yml` — `setup`, `run`, `debug`, `release` (+ `db:migrate`/`db:revision` for DB services)
- `config/` — committed local defaults
- `data/` — runtime data (gitignored)

The DCAT-AP catalogue and governed query API live in the separate `celine-eu/celine-dev` repository under `repositories/dataset-api`, port 30002.

---

## Services

### ds-connector (`services/connector`)

The central orchestration layer. Wraps both an EDC provider and consumer connector instance, exposes a clean REST API for governance sync, consumer data flows, consent management, and participant registry lookups. Uses PostgreSQL via async SQLAlchemy + Alembic.

### ds-provenance (`services/provenance`)

A W3C PROV-O compatible REST API that logs catalogue publication, contract negotiation, data transfer, and obligation fulfilment events as linked-data graph nodes. Uses a relational database with BFS lineage traversal — no triple stores.

### ds-portal (`services/portal`)

A SvelteKit web application covering the full portal surface: catalogue browser, consumer negotiation wizard, provider governance management, consent portal for data subjects, and provenance lineage viewer.

### ds-sts (`services/sts`)

A minimal Security Token Service. Each participant runs their own instance (provider + consumer). Issues ES256-signed Self-Issued tokens (SI JWTs) with the participant DID as `sub` and `iss`, consumed by EDC during DCP handshake.

### ds-vc-wallet (`services/vc-wallet`)

A minimal DCP Credential Service. Holds pre-issued Verifiable Credentials and returns them as a `VerifiablePresentation` when queried by EDC during contract negotiation.

### ds-federated-catalog (`services/federated-catalog`)

A DCAT-AP catalog crawler. Periodically queries participant connectors and builds an aggregated catalog. Backed by the connector's participant registry.

### edc-extensions (`services/edc-extensions`)

Java extensions for the EDC policy engine. Registers three `AtomicConstraintFunction` implementations for the `ds:` ODRL vocabulary: `ds:accessScope` (participant allowlist), `ds:consentStatus` (consent registry check), and `ds:contractRequired` (bilateral contract gate).

### edc-connector (`services/edc-connector`)

Gradle project that assembles a fat JAR combining `controlplane-dcp-bom`, `dataplane-base-bom`, `configuration-filesystem`, `identity-did-web`, and `edc-extensions` against EDC v0.16.0. Built via a versioned base image (`ds-edc-base:0.16.0`) that pre-caches all Maven dependencies.

---

## How services interact

```
                                   ┌─────────────────────────┐
                                   │     Portal (30004)      │
                                   │     SvelteKit + Auth.js │
                                   └────────┬───────┬────────┘
                                            │       │
                              ┌─────────────┘       └─────────────┐
                              ▼                                   ▼
                    ┌──────────────────┐               ┌──────────────────┐
                    │  ds-connector    │               │  ds-provenance   │
                    │  (30001)         │               │  (30000)         │
                    │  FastAPI         │──events──────→│  FastAPI         │
                    └──┬────┬────┬────┘               └──────────────────┘
                       │    │    │
          ┌────────────┘    │    └────────────┐
          ▼                 ▼                 ▼
  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ EDC Provider │  │ EDC Consumer │  │ Federated Catalog │
  │ (19191-19291)│  │ (29191-29291)│  │ (30003)           │
  └──┬───────┬───┘  └──┬───────┬──┘  └──────────────────┘
     │       │         │       │
     ▼       ▼         ▼       ▼
  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
  │ STS  │ │ VC   │ │ STS  │ │ VC   │
  │38080 │ │Wallet│ │38081 │ │Wallet│
  └──────┘ │38082 │ └──────┘ │38083 │
           └──────┘          └──────┘
```

**Portal** is the user-facing frontend. All data operations go through **ds-connector**, which orchestrates EDC, consent, and governance. During DSP negotiation, EDC connectors call **STS** for identity tokens and **VC-wallet** for credential presentations. EDC also calls back to ds-connector's `/internal/*` endpoints for ODRL constraint evaluation (via **edc-extensions**). **ds-provenance** is a pure event sink — it receives lifecycle events from ds-connector and serves lineage queries to the portal. **Federated catalog** crawls participant DSP endpoints periodically. The external **dataset-api** (port 30002) validates agreements and consent via ds-connector before returning query results.

For detailed interaction diagrams, see:

- [Architecture overview](docs/architecture.md) — service map, network topology, port scheme
- [Data exchange flow](docs/data-exchange-flow.md) — step-by-step negotiation and transfer sequence
- [Identity & DCP](docs/identity-and-dcp.md) — DID, STS, VC-wallet, DCP verification flow
- [Governance & ODRL](docs/governance-and-odrl.md) — YAML to ODRL pipeline and policy enforcement
- [Provenance & lineage](docs/provenance-and-lineage.md) — event types, PROV-O model, graph traversal
- [Consent & sovereignty](docs/consent-and-sovereignty.md) — consent lifecycle, row filtering, revocation

---

## Getting started

### Prerequisites

- Docker with Compose (v2.24+)
- Python 3.12 (for key generation and VC issuance scripts)

### One-time workspace setup

Generate participant key pairs and issue membership VCs:

```bash
bash scripts/gen-keys.sh     # EC P-256 key pairs → data/keys/
python3 scripts/issue-vcs.py # MembershipCredential VCs → data/credentials/
```

Optionally add the local hostnames to `/etc/hosts` and trust Caddy's CA:

```bash
task proxy:hosts     # adds *.dataspaces.localhost entries (requires sudo)
task proxy:trust-ca  # trusts Caddy root CA in system store (requires sudo)
```

### Start the full stack

```bash
# 1. Start shared infra (caddy + postgres on port 35432)
docker compose up -d

# 2. Start all service stacks
task services:start

# Or both at once:
task start
```

### Local development (replace one container with a local process)

```bash
docker compose up -d
task services:start

# Stop just the service you want to develop
docker compose -f services/connector/docker-compose.yml stop ds-connector

# Run it locally (postgres still running in docker)
cd services/connector
task setup   # first time only
task run
```

### Build the EDC connector image

```bash
# Build the dependency cache base image (once per EDC version bump)
task edc:base

# Build the connector image
task edc:docker
```

### Verify the stack

After services are up, the following should respond:

- `https://connector.dataspaces.localhost/health`
- `https://provenance.dataspaces.localhost/health`
- `https://portal.dataspaces.localhost`
- `https://provider.dataspaces.localhost/.well-known/did.json`
- `https://consumer.dataspaces.localhost/.well-known/did.json`
- `https://trust-anchor.dataspaces.localhost/.well-known/did.json`

---

## Infrastructure

### Shared services (root `docker-compose.yml`)

| Service | Image | Port | Notes |
|---------|-------|------|-------|
| caddy | `caddy:2-alpine` | 80, 443 | Reverse proxy, local HTTPS, DID document serving |
| postgres | `postgres:17.4-alpine` | 35432 | One database per service (`connector`, `provenance`, …) |

All services share the `dataspaces` Docker network. The `postgres` container is reachable as `postgres:5432` from within the network and as `host.docker.internal:35432` from the host.

### Pydantic settings defaults

All Python services use `pydantic-settings` with hard defaults pointing at the shared postgres. No `.env` file is required to run locally — override via environment variables when needed.

`.env.example` files are documentation only.

---

## Participant identities

Each participant is identified by a `did:web:` URI:

- Provider: `did:web:provider.dataspaces.localhost`
- Consumer: `did:web:consumer.dataspaces.localhost`
- Trust anchor: `did:web:trust-anchor.dataspaces.localhost`

DID documents are static JSON files served by Caddy from `services/caddy/did/`. Each document contains an EC P-256 `JsonWebKey2020` verification method used for DCP identity proofs.

Private keys live in `services/connector/config/*-key.json` (dev only — inject via secrets manager in production).

---

## Governance and ODRL policies

Datasets are described in `governance.yaml` files following the CELINE governance schema extended with `dcat:` and `dataspace:` blocks. The `GovernanceMapper` in `services/governance/` converts these into ODRL Offer policies attached to EDC assets.

Access levels map to ODRL as follows:

- `open` — no constraints; `downloadURL` included in DCAT distribution
- `internal` — `ds:accessScope eq "dataspaces.query"` constraint
- `restricted` — scope constraint plus `ds:contractRequired eq "true"`
- `secret` — not exposed to EDC or the catalogue

When `user_filter_column` is set on a dataset, a `ds:consentStatus eq active` constraint is added to the ODRL offer and consent-based row filtering is applied at query time.

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

## DCP identity verification

During DSP negotiation, each connector presents a signed Verifiable Presentation containing a `MembershipCredential` issued by the trust anchor. The counterparty verifies:

1. The VP signature matches the holder's DID document public key
2. The VC was issued by a trusted issuer (`edc.iam.trustedissuer.0.id`)
3. ODRL constraints are evaluated against the verified participant identity

The STS service issues ES256 SI tokens on demand via OAuth2 `client_credentials`. The VC wallet returns held credentials when EDC queries the DCP Credential Service API.

---

## License

Copyright © 2025 Spindox Labs

Licensed under the Apache License, Version 2.0.
