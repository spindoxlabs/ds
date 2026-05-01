# Dataspaces — Agent Guide

## What this repo is

A DSSC Blueprint-aligned dataspace platform for energy communities. Implements the full consumer-pull data exchange flow: catalogue discovery, contract negotiation (ODRL), EDR-gated data transfer, consent-based row filtering, and W3C PROV-O provenance tracking.

Built on Eclipse Dataspace Connector (v0.16.0) with Python/FastAPI orchestration and a SvelteKit frontend.

## Repository structure

```
dataspaces/
├── services/
│   ├── connector/          Python/FastAPI — EDC orchestration, consent, governance sync
│   ├── provenance/         Python/FastAPI — W3C PROV-O event logging and lineage
│   ├── portal/             SvelteKit — web frontend for all participant roles
│   ├── governance/         Python library — GovernanceRuleV2, ODRL mapper
│   ├── sts/                Python/FastAPI — Security Token Service (ES256 SI JWTs)
│   ├── vc-wallet/          Python/FastAPI — DCP Credential Service (VP queries)
│   ├── federated-catalog/  Python/FastAPI — DCAT-AP catalog crawler
│   ├── edc-extensions/     Java — custom ODRL constraint functions for EDC
│   ├── edc-connector/      Gradle — EDC fat JAR build (DCP-enabled, v0.16.0)
│   └── caddy/              Config — reverse proxy, TLS, DID document hosting
├── docs/                   Architecture docs, DSSC blueprint reference
├── scripts/                Key generation, VC issuance
├── data/                   Runtime data (gitignored) — keys, credentials, caddy PKI
├── docker-compose.yml      Shared infra — caddy + postgres
├── Taskfile.yml            Root orchestration
├── build.gradle.kts        Gradle root for Java subprojects
└── settings.gradle.kts     Includes edc-extensions + edc-connector
```

Each service has its own `AGENTS.md`, `README.md`, `Dockerfile`, `docker-compose.yml`, and `Taskfile.yml`.

## Service interaction map

```
Portal (30004) ──→ ds-connector (30001) ──→ EDC Provider/Consumer
                                        ──→ ds-provenance (30000)
                                        ──→ Federated Catalog (30003)

EDC Provider ←──DSP──→ EDC Consumer
  ├──→ STS (38080/38081)         SI token issuance
  ├──→ VC-wallet (38082/38083)   VP queries
  └──→ ds-connector /internal/*  ODRL constraint evaluation

dataset-api (30002, external) ──→ ds-connector /internal/*  agreement + consent checks
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Python services | FastAPI, SQLAlchemy async, Alembic, Pydantic, httpx |
| Frontend | SvelteKit 2.0, Svelte 5.0, Tailwind CSS 4.0, Cytoscape.js |
| Identity | Eclipse EDC 0.16.0, `did:web:`, DCP, ES256 JWTs |
| Database | PostgreSQL 17.4 (one DB per service) |
| Proxy | Caddy 2 (local HTTPS, DID hosting) |
| Auth | Keycloak OIDC via Auth.js |
| Build | uv (Python), npm (Node), Gradle (Java), Taskfile |
| Containers | Docker Compose, multi-stage Dockerfiles |

## Coding conventions

### Python services

- Python 3.12, FastAPI, async throughout
- `pydantic-settings` for config — defaults work for local dev, override via env vars
- Package structure: `src/<package>/{main,config,services/,clients/,api/,db/,schemas/}.py`
- Use `httpx.AsyncClient` for HTTP, never `requests`
- Database access via async SQLAlchemy sessions
- Alembic for migrations: `task db:revision MESSAGE=...`, `task db:migrate`
- Linting: `ruff`, type checking: `mypy`, testing: `pytest` + `pytest-asyncio`
- Use `uv` for dependency management

### Frontend (Portal)

- SvelteKit 2.0 with Svelte 5 runes (`$state`, `$derived`, `$effect`)
- Mobile-first with Tailwind CSS
- SSR data loading — API calls in `+page.server.ts`, never in client components
- Auth.js for Keycloak OIDC, role-based guards in `src/lib/server/auth.ts`

### Java (EDC extensions)

- Java 21, Gradle with Shadow plugin
- EDC SPI interfaces — `AtomicConstraintFunction<Permission>`
- Use `Monitor` for logging (EDC's abstraction)
- Build: `gradle :edc-extensions:build`, `gradle :edc-connector:shadowJar`

### General

- Each service runs via `task run` (no global orchestration needed for dev)
- Port scheme: 30000+ for services, 30900+ for debuggers, 19xxx/29xxx for EDC
- All `*.dataspaces.localhost` domains resolve locally via Caddy
- No `.env` files required — all defaults baked into settings classes
- Docker network: `dataspaces` (bridge), all containers share it

## Governance and policy model

Datasets are declared in `services/connector/governance/governance.yaml`. The pipeline:

```
governance.yaml → GovernanceResolver → GovernanceRuleV2 → GovernanceMapper
  → ODRL Offer + EDC Asset + EDC PolicyDefinition + EDC ContractDefinition
  → POST /provider/sync pushes to EDC Management API
  → EDC serves to consumers via DSP
  → edc-extensions evaluate constraints at negotiation time
```

See `docs/governance-and-odrl.md` for the full pipeline documentation.

## Quick start

```bash
# One-time setup
bash scripts/gen-keys.sh          # EC P-256 key pairs
python3 scripts/issue-vcs.py      # membership VCs
task proxy:hosts                  # /etc/hosts entries (sudo)
task proxy:trust-ca               # trust Caddy CA (sudo)

# Start everything
task start

# Or start shared infra + individual service stacks
docker compose up -d
task services:start
```

## Key documentation

| Document | Path |
|----------|------|
| Architecture overview | `docs/architecture.md` |
| Governance & ODRL pipeline | `docs/governance-and-odrl.md` |
| Identity & DCP flow | `docs/identity-and-dcp.md` |
| Data exchange flow | `docs/data-exchange-flow.md` |
| Provenance & lineage | `docs/provenance-and-lineage.md` |
| Consent & sovereignty | `docs/consent-and-sovereignty.md` |
| DSSC Blueprint reference | `docs/dssc-blueprint-docs/` |
| Per-service guides | `services/*/AGENTS.md` and `services/*/README.md` |

## Common agent tasks

| Task | Where to start |
|------|---------------|
| Add a new dataset to the catalogue | `services/connector/governance/governance.yaml` |
| Add a new ODRL constraint type | `services/governance/` (mapper) + `services/edc-extensions/` (function) |
| Add a new API endpoint to connector | `services/connector/src/connector/api/v1/` |
| Add a new portal page | `services/portal/src/routes/` |
| Add a new provenance event type | `services/provenance/src/provenance/schemas/events.py` + `services/connector/src/connector/services/prov_bridge.py` |
| Change consent behavior | `services/connector/src/connector/services/consent_service.py` |
| Add a new participant | `services/connector/governance/participants.yaml` + `services/caddy/did/` + `scripts/` |
| Modify EDC connector build | `services/edc-connector/build.gradle.kts` |
