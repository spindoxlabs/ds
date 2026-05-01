# Services Architecture

This document describes the overall architecture: how services are organized, how they communicate, and the deployment topology.

---

## Service map

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

### Shared infrastructure (root docker-compose.yml)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| Caddy | `caddy:2-alpine` | 80, 443 | Reverse proxy, TLS termination, DID doc hosting |
| PostgreSQL | `postgres:17.4-alpine` | 35432 | Shared database (one DB per service) |

---

## Communication patterns

### Synchronous HTTP

All inter-service communication uses HTTP REST:

| Caller | Callee | Protocol | Purpose |
|--------|--------|----------|---------|
| Portal | ds-connector | HTTP (SSR) | All data operations |
| Portal | ds-provenance | HTTP (SSR) | Lineage, audit queries |
| ds-connector | EDC Provider/Consumer | EDC Management API v3 | Asset/policy CRUD, negotiation, transfer |
| ds-connector | ds-provenance | HTTP | Emit provenance events |
| EDC | STS | OAuth2 client_credentials | SI token issuance |
| EDC | VC-wallet | DCP Credential Service API | VP queries |
| EDC | ds-connector | HTTP | Internal constraint checks |
| EDC Provider ↔ EDC Consumer | DSP | Contract negotiation, transfer |
| dataset-api | ds-connector | HTTP | Agreement validation, consent check |
| Federated catalog | ds-connector | HTTP | Catalog proxy, participant registry |

### No message queues

The architecture is fully synchronous. There are no message brokers, event buses, or async messaging systems. Provenance events are emitted via HTTP POST (fire-and-forget with retry via `tenacity`).

---

## Network topology

All services share a single Docker bridge network named `dataspaces`. Internal service-to-service calls use container hostnames (e.g. `edc-provider:19194`). External access goes through Caddy's HTTPS reverse proxy.

```
Internet / Browser
       │
       ▼
    Caddy (443)
       │
       ├──→ host.docker.internal:30004  (portal)
       ├──→ host.docker.internal:30001  (connector)
       ├──→ host.docker.internal:30000  (provenance)
       ├──→ host.docker.internal:30003  (federated-catalog)
       ├──→ edc-provider:19194          (DSP protocol)
       ├──→ edc-consumer:29194          (DSP protocol)
       └──→ host.docker.internal:8080   (keycloak)
```

Services running locally (outside Docker) use `host.docker.internal` to reach containers. Services running inside Docker use container names directly.

---

## Database layout

A single PostgreSQL instance hosts multiple databases:

| Database | Owner | Tables |
|----------|-------|--------|
| `connector` | ds-connector | consent_records, transfer_tracking |
| `provenance` | ds-provenance | prov_nodes, prov_relations, domain_events |

Each service manages its own schema via Alembic migrations. There are no cross-database queries.

---

## Auth and identity layers

### User authentication (Portal)

```
Browser → Portal → Keycloak (OIDC)
```

Auth.js handles the OIDC flow. Keycloak issues JWTs with roles (`admin`, `dataset.admin`) and scopes (`dataspaces.query`). The portal derives a `UserPersona` to gate UI sections.

### Machine authentication (EDC ↔ EDC)

```
EDC → STS (SI token) → EDC
EDC → VC-wallet (VP) → EDC
```

During DSP negotiation, each EDC instance obtains an SI token from its STS and a VP from its VC wallet. The counterparty verifies both against the sender's DID document.

### Internal API authentication

ds-connector's `/internal/*` endpoints are called by EDC extensions and dataset-api. In the current dev setup these are unauthenticated (network-level trust). In production, secure with API keys or mTLS.

---

## Port scheme

| Range | Purpose | Examples |
|-------|---------|---------|
| 30000-30009 | Python/Node services | provenance:30000, connector:30001, dataset-api:30002, catalog:30003, portal:30004 |
| 30900-30909 | Debug ports | provenance:30900, connector:30901 |
| 19191-19291 | EDC provider | mgmt:19191, DSP:19194, data:19291 |
| 29191-29291 | EDC consumer | mgmt:29191, DSP:29194, data:29291 |
| 38080-38083 | DCP services | STS:38080-38081, wallet:38082-38083 |
| 35432 | PostgreSQL | shared instance |
| 8080 | Keycloak | auth server |

---

## Deployment modes

### Local development (full Docker)

```bash
task start    # shared infra + all service stacks
```

All services run in containers on the `dataspaces` network.

### Local development (hybrid)

```bash
docker compose up -d          # shared infra
task services:start           # all service stacks
# Stop the service you want to develop locally:
docker compose -f services/connector/docker-compose.yml stop ds-connector
cd services/connector && task run
```

The local process connects to PostgreSQL via `host.docker.internal:35432` and to other services via their container ports.

### Production

Each service has a `Dockerfile` and optional `charts/` directory for Helm deployment. The architecture assumes:
- External PostgreSQL (managed service)
- External Keycloak (or compatible OIDC provider)
- External secret management (replace dev key files)
- Ingress controller (replace Caddy)

---

## DSSC Blueprint building block coverage

| BB | Name | Service(s) |
|----|------|-----------|
| BB01 | Trust Framework | Trust anchor DID + VC issuance (scripts/) |
| BB02 | Identity & Attestation | STS, VC-wallet, Caddy (DID docs) |
| BB03 | Access & Usage Policies | Governance lib, edc-extensions |
| BB04 | Data Offerings & Descriptions | Federated catalog, governance.yaml |
| BB05 | Publication & Discovery | EDC DSP, federated catalog |
| BB06 | Data Exchange | EDC connector, ds-connector |
| BB07 | Provenance & Traceability | ds-provenance |
| BB08 | Vocabulary Hub | ds: namespace (connector /ns/energy) |
| BB09 | Data Sovereignty | Consent system in ds-connector |
| DCP | Dataspace Credential Protocol | EDC + STS + VC-wallet |
