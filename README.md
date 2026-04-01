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
├── src/ds/
│   ├── connector/      port 30001 — EDC control-plane orchestrator (Python/FastAPI)
│   ├── provenance/     port 30000 — PROV-O REST API (Python/FastAPI)
│   ├── portal/         port 30004 — Dataspace web frontend (SvelteKit)
│   ├── governance/     shared library — GovernanceRuleV2 models and ODRL mapper
│   ├── sts/            port 38080/38081 — Security Token Service (Python/FastAPI)
│   └── vc_wallet/      port 38082/38083 — Credential Service (Python/FastAPI)
├── edc-extensions/     Java — custom ODRL constraint functions for EDC
├── edc-connector/      Java (Gradle) — DCP-enabled EDC connector fat JAR
├── caddy/              Reverse proxy config and static DID document hosting
├── charts/             Helm charts per service
├── docs/               Plans, status docs, next phases
└── scripts/            Key generation, VC issuance
```

The DCAT-AP catalogue and governed query API live in the separate `celine-eu/celine-dev` repository under `repositories/dataset-api`, port 30002.

---

## Services

### ds-connector

The central orchestration layer. Wraps both an EDC provider and consumer connector instance, exposes a clean REST API for governance sync, consumer data flows, consent management, and participant registry lookups.

See `src/ds/connector/README.md`.

### ds-provenance

A W3C PROV-O compatible REST API that logs catalogue publication, contract negotiation, data transfer, and obligation fulfilment events as linked-data graph nodes. Uses a relational database with BFS lineage traversal — no triple stores.

See `src/ds/provenance/README.md`.

### ds-portal

A SvelteKit web application covering the full portal surface: catalogue browser, consumer negotiation wizard, provider governance management, consent portal for data subjects, and provenance lineage viewer.

See `src/ds/portal/README.md`.

### ds-sts

A minimal Security Token Service. Each participant runs their own instance. Issues ES256-signed Self-Issued tokens (SI JWTs) with the participant DID as `sub` and `iss`, consumed by EDC during DCP handshake.

See `src/ds/sts/README.md`.

### ds-vc-wallet

A minimal DCP Credential Service. Holds pre-issued Verifiable Credentials and returns them as a `VerifiablePresentation` when queried by EDC during contract negotiation.

See `src/ds/vc_wallet/README.md`.

### edc-extensions

Java extensions for the EDC policy engine. Registers three `AtomicConstraintFunction` implementations for the `ds:` ODRL vocabulary: `ds:accessScope` (participant allowlist), `ds:consentStatus` (consent registry check), and `ds:contractRequired` (bilateral contract gate).

See `edc-extensions/README.md`.

### edc-connector

Gradle project that builds a fat JAR combining the EDC `controlplane-dcp-bom` with `edc-extensions`. This replaces the EDC samples connector from the MVP phases and activates full DCP identity verification.

See `edc-connector/README.md`.

---

## Getting started

### Prerequisites

- Docker with Compose
- Java 21 (for building the EDC connector JAR)
- Python 3.12 with `cryptography` package (for key generation and VC issuance)

### Initial setup

Generate participant key pairs and issue membership VCs:

```bash
python3 scripts/gen-keys.sh   # regenerate EC P-256 key pairs
python3 scripts/issue-vcs.py  # issue MembershipCredential VCs signed by trust anchor
```

### Build the DCP connector JAR

```bash
./gradlew :edc-connector:shadowJar
```

### Start all services

Each service has its own `docker-compose.yml`. Use the top-level compose files for integration:

```bash
# Dev proxy (Caddy — serves DID documents and reverse proxies all services)
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up caddy

# Full connector stack (EDC + STS + VC wallet + ds-connector + db)
docker compose -f src/ds/connector/docker-compose.yml up

# Portal
docker compose -f src/ds/portal/docker-compose.yml up

# Provenance
docker compose -f src/ds/provenance/docker-compose.yml up
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

## Participant identities

Each participant is identified by a `did:web:` URI:

- Provider: `did:web:provider.dataspaces.localhost`
- Consumer: `did:web:consumer.dataspaces.localhost`
- Trust anchor: `did:web:trust-anchor.dataspaces.localhost`

DID documents are static JSON files served by Caddy under `caddy/did/`. Each document contains an EC P-256 `JsonWebKey2020` verification method used for DCP identity proofs.

Private keys live in `src/ds/connector/config/*-key.json` (dev only — inject via secrets manager in production).

---

## Governance and ODRL policies

Datasets are described in `governance.yaml` files following the CELINE governance schema extended with `dcat:` and `dataspace:` blocks. The `GovernanceMapper` in `src/ds/governance/` converts these into ODRL Offer policies attached to EDC assets.

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

## DCP identity verification (Iteration 5)

During DSP negotiation, each connector presents a signed Verifiable Presentation containing a `MembershipCredential` issued by the trust anchor. The counterparty verifies:

1. The VP signature matches the holder's DID document public key
2. The VC was issued by a trusted issuer (`edc.iam.trustedissuer.0.id`)
3. ODRL constraints are evaluated against the verified participant identity

The STS service issues ES256 SI tokens on demand via OAuth2 `client_credentials`. The VC wallet returns held credentials when EDC queries the DCP Credential Service API.

---

## Development status

All MVP phases (0–5) and post-MVP Iterations 4 and 5 are complete. See `docs/status/README.md` for the full per-service breakdown and `docs/next-phases.md` for the remaining backlog (Iterations 2, 6, 7).

---

## Documentation

- `docs/plans/` — per-service implementation plans
- `docs/status/` — per-service completion status and implementation notes
- `docs/next-phases.md` — post-MVP backlog ordered by dependency
- `docs/dssc-blueprint-docs/` — DSSC Blueprint v3.0 building block references

---

## License

Copyright © 2025 Spindox Labs

Licensed under the Apache License, Version 2.0.
