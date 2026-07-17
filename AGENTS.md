# Dataspaces — Agent Guide

## What this repo is

A DSSC Blueprint-aligned dataspace platform for energy communities. Implements the full consumer-pull data exchange flow: catalogue discovery, contract negotiation (ODRL), EDR-gated data transfer, consent-based row filtering, and W3C PROV-O provenance tracking.

Built on Eclipse Dataspace Connector (v0.16.0) with Python/FastAPI orchestration and a SvelteKit frontend.

The approach should be generalizable and support different use-cases, ensure to not over specify or specialize on a domain. 

Domain specific implementaion should be oriented toward modularization and extension of the platform.

## Privacy

Integration to data plane components should not expose private organizations references or cross-project requirements and references in this reposiotories.

Ensure to not cite organizations, projects and datasets that are not public and not explicitly allowed by the user.

This apply to all resource such as docs, tests, codebase, AGENTS.md, samples and dev defaults.

## Repository structure

```
dataspaces/
├── services/
│   ├── connector/              Python/FastAPI — EDC orchestration, consent, governance sync
│   ├── provenance/             Python/FastAPI — W3C PROV-O event logging and lineage
│   ├── portal/                 SvelteKit — web frontend for all participant roles
│   ├── identity-registry/      Python/FastAPI — DID lifecycle, STS, credential service, participant registry
│   ├── federated-catalog/      Python/FastAPI — DCAT-AP catalog crawler
│   ├── dataset-api-mock/       Python/FastAPI — mock dataset API for dev
│   ├── dataset-api-fiware-adapter/  Python — FIWARE NGSI-LD adapter
│   ├── edc-extensions/         Java — custom ODRL constraint functions for EDC
│   ├── edc-connector/          Gradle — EDC fat JAR build (DCP-enabled, v0.16.0)
│   ├── caddy/                  Config — reverse proxy, TLS, DID document routing
│   └── keycloak/               Config — OIDC realm import for dev
├── libs/                       Importable shared Python packages (no Dockerfile, no port)
│   ├── governance/             ds-governance — GovernanceRuleV2, ODRL mapper (import `ds.governance`)
│   └── ds-auth/                ds-auth — JWT auth + unified scope/group authorization (import `ds_auth`)
├── docs/                       Architecture docs, DSSC blueprint reference
├── scripts/                    Bootstrap, compliance validation, backup
├── data/                       Runtime data (gitignored) — caddy PKI, gradle cache
├── docker-compose.yml          Shared infra — caddy, postgres, identity-registry, keycloak
├── docker-compose.provider.yml Provider participant stack
├── docker-compose.consumer.yml Consumer participant stack
├── Taskfile.yml                Root orchestration
├── build.gradle.kts            Gradle root for Java subprojects
└── settings.gradle.kts         Includes edc-extensions + edc-connector
```

Each service has its own `Taskfile.yml` and `Dockerfile`. Most have an `AGENTS.md` and `README.md`.

**When working on a specific service, always load its `services/<name>/AGENTS.md` first.** It contains the source layout, key files, coding conventions, and integration points specific to that service.

### Shared libraries: `libs/`

Importable Python packages shared across services live under **`libs/`**, not `services/`. The rule:

- **`libs/`** — a package with no `Dockerfile` and no port; consumed via an editable path dependency. Today: `libs/governance` (`ds-governance`, imported as `ds.governance`) and `libs/ds-auth` (`ds-auth`, imported as `ds_auth`).
- **`services/`** — a deployable unit with a `Dockerfile` and a `task <participant>:<service>:run`.

To depend on a lib, add it to the service's `pyproject.toml` `[project].dependencies` and point `[tool.uv.sources]` at it, e.g. `ds-auth = { path = "../../libs/ds-auth", editable = true }`. In the service `Dockerfile`, `COPY libs/<lib>/ /build/<lib>/`, `uv pip install` it, and strip its name from the copied `pyproject.toml` before installing the rest (see `services/connector/Dockerfile`). New shared code goes in `libs/`; never add a library under `services/`.

## Service interaction map

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
  ├── Participant registry GET /participants, GET /participants/{did}/check
  └── StatusList2021     GET /status/{list_id}

Federated Catalog (30003) ──→ identity-registry /participants (provider discovery)
ds-connector ──→ identity-registry /participants (HttpParticipantRegistry with TTL cache)

dataset-api (30002, external) ──→ ds-connector /internal/*  agreement + consent checks
```

## Compose topology

Three compose files form the full stack:

| File | Services | Purpose |
|------|----------|---------|
| `docker-compose.yml` | caddy, postgres, identity-registry, keycloak, keycloak-sync | Shared infrastructure |
| `docker-compose.provider.yml` | edc-provider, ds-connector-provider, ds-provenance-provider, dataset-api-provider, ds-federated-catalog-provider, ds-portal | Provider participant |
| `docker-compose.consumer.yml` | edc-consumer, ds-connector-consumer, ds-provenance-consumer | Consumer participant |

The portal runs in the provider compose. For local dev with hot-reload: `task provider:portal:run`.

All containers share the `dataspaces` bridge network.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Python services | FastAPI, SQLAlchemy async, Alembic, Pydantic, httpx |
| Frontend | SvelteKit 2.0, Svelte 5.0, Tailwind CSS 4.0, Cytoscape.js |
| Identity (BB02) | identity-registry: DID lifecycle, STS (ES256 SI JWTs), DCP credential service, participant registry, StatusList2021 |
| Data exchange (BB05) | Eclipse EDC 0.16.0, `did:web:`, DCP, ODRL, DSP |
| Database | PostgreSQL 17.4 (one DB per service, all on port 35432) |
| Proxy | Caddy 2 (HTTP reverse proxy, DID document routing to identity-registry) |
| Auth | Keycloak OIDC via Auth.js |
| Build | uv (Python), npm (Node), Gradle (Java), Taskfile |
| Containers | Docker Compose, multi-stage Dockerfiles |

## Port scheme

| Port | Service |
|------|---------|
| 30000 | ds-provenance (provider) |
| 30001 | ds-connector (provider) |
| 30002 | dataset-api (provider) |
| 30003 | federated-catalog (provider) |
| 30004 | portal (standalone, run locally) |
| 30005 | identity-registry (shared infra) |
| 31000 | ds-provenance (consumer) |
| 31001 | ds-connector (consumer) |
| 35432 | PostgreSQL |
| 8080 | Keycloak |
| 9000 | Caddy consumer gateway |
| 9010 | Caddy provider gateway |
| 19xxx | EDC provider (management, protocol, public, control) |
| 29xxx | EDC consumer (management, protocol, public, control) |
| 30900+ | debugpy ports |

## Identity architecture

The identity-registry is a centralized trust anchor service (DSSC BB02 — Identity & Attestation). It replaces previously separate STS, VC-wallet, and static DID file services.

**Key principle:** DID private keys never leave the identity-registry. The EDC vault contains only a separate EDR signing key used for Endpoint Data Reference tokens.

**Encryption at rest:** Private keys are Fernet-encrypted in the database using `IDENTITY_REGISTRY_ENCRYPTION_KEY`. STS client secrets are PBKDF2-hashed (never stored in cleartext). The dev default key works out of the box; production deployments must set a strong key.

How DID resolution works:
1. EDC resolves `did:web:provider.dataspaces.localhost` by fetching `http://provider.dataspaces.localhost/.well-known/did.json`
2. Caddy rewrites this to `/dids/did:web:provider.dataspaces.localhost/did.json` and proxies to identity-registry
3. The identity-registry builds and returns the DID document from its database

The `ir-cli` tool (installed in the identity-registry container) handles bootstrap and participant registration. See `task identity:bootstrap` for the full setup sequence.

## Deployment / helm chart notes

The following must be addressed when preparing the helm chart:

- **IDENTITY_REGISTRY_ENCRYPTION_KEY**: Must be set to a strong random value. Used for Fernet encryption of DID private keys at rest. Losing this key means losing access to all stored private keys.
- **IDENTITY_REGISTRY_OIDC_ISSUER_URL**: Must be set in production. Without it, admin endpoints accept unverified JWTs (acceptable in dev, critical vulnerability in production).
- **IDENTITY_REGISTRY_ADMIN_SCOPE**: Defaults to `identity-registry.admin`. Configure in Keycloak realm.
- **EDC vault properties** (`consumer-vault.properties`, `provider-vault.properties`): Contain EDR signing keys and STS client secrets. In dev, placeholder keys and `insecure-dev-secret` are used. Production deployments must generate real EC P-256 keys and strong STS secrets, injected via Kubernetes secrets.
- **EDC_API_KEY**: Defaults to `insecure-dev-key`. Must be overridden with a strong random value.
- **AUTH_SECRET**: Used by Auth.js for session encryption. Must be a strong random value.
- `.env.production.example` is the authoritative reference for all production env vars.

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
- Port scheme: 30000+ for Python services, 30900+ for debuggers, 19xxx/29xxx for EDC
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
task proxy:hosts                  # /etc/hosts entries (sudo)
task proxy:trust-ca               # trust Caddy CA (sudo)

# Start everything (infra + identity bootstrap + provider + consumer)
task start

# Or step by step:
task infra:start                  # shared infra (postgres, caddy, identity-registry, keycloak)
task identity:bootstrap           # trust anchor + participant registration
task provider:start               # provider stack (EDC + connector + provenance + dataset-api + catalog)
task consumer:start               # consumer stack (EDC + connector + provenance)
task provider:portal:run          # portal locally with hot-reload (optional)
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
| Add a new ODRL constraint type | `libs/governance/` (mapper) + `services/edc-extensions/` (function) |
| Add a new API endpoint to connector | `services/connector/src/connector/api/v1/` |
| Add a new portal page | `services/portal/src/routes/` |
| Add a new provenance event type | `services/provenance/src/provenance/schemas/events.py` + `services/connector/src/connector/services/prov_bridge.py` |
| Change consent behavior | `services/connector/src/connector/services/consent_service.py` |
| Add a new participant | `task identity:bootstrap` or `ir-cli participant add` in the identity-registry container |
| Add identity-registry API endpoints | `services/identity-registry/src/identity_registry/api/v1/` |
| Modify EDC connector build | `services/edc-connector/build.gradle.kts` |
| Issue a new credential type | `services/identity-registry/src/identity_registry/services/vc.py` + `admin.py` |

## Gotchas

- **Async SQLAlchemy sessions auto-begin.** Never call `session.begin()` inside `async with factory() as session:` — just do the work and `await session.commit()`.
- **Dockerfiles use repo root as build context.** `COPY` paths in `services/*/Dockerfile` are relative to root, not the service directory. `.dockerignore` at root excludes `data/`, `.git`, `node_modules`, `.venv`.
- **Python services must be installed as packages** in Dockerfiles (`uv pip install .`) so console script entry points (e.g., `ir-cli`) are created. Don't manually list deps.
- **`172.17.0.1`** is the standard host-gateway address in all compose files.
- `uv run` for python commands is generally better in the context of a service.

## Dev environment conventions

### URL addressing

Two address schemes depending on the call direction:

| Context | Scheme | Example |
|---------|--------|---------|
| Browser-facing / OIDC issuer / ORIGIN / callback URLs | Caddy-proxied `*.dataspaces.localhost` | `http://keycloak.dataspaces.localhost:9010/realms/dataspaces` |
| Container-to-host or host-to-container backend calls | `172.17.0.1:<port>` | `http://172.17.0.1:30005` |
| Container-to-container (inside compose) | Docker DNS service name | `http://identity-registry:30005` |

Never use raw `localhost:<port>` for service URLs — it's ambiguous across host/container boundaries. Use `172.17.0.1` or the Caddy-proxied domain.

Caddy gateway ports: `:9010` (provider), `:9000` (consumer).

### Running services locally

Every service has a `task <participant>:<service>:run` command in the root Taskfile that stops the Docker container and runs the service locally with hot-reload. Environment variables are set to use `172.17.0.1` for backend services and Caddy-proxied domains for browser-facing URLs. This allows running one service locally while the rest remain in Docker.

### Idempotency

All bootstrap and provisioning operations must be idempotent. `task identity:bootstrap` can be run repeatedly without duplicating participants or credentials. `ir-cli` commands use upsert semantics. Alembic migrations are tracked and skip already-applied revisions. Database init containers check for existing databases before creating them.

### Dev credentials

| User | Password | KC roles | VC role | Purpose |
|------|----------|----------|---------|---------|
| `admin@example.test` | `admin` | `ds-admin`, `dataset.admin`, portal `admin` | — | Platform admin |
| `provider@example.test` | `provider` | `dataset.admin`, portal `dataset.admin` | — | Dataset provider |
| `consumer@example.test` | `consumer` | — | `ConsumerUser` | Data consumer |
| `subject@example.test` | `subject` | — | `DataSubject` | Consent management |

Service accounts are defined in `services/keycloak/clients.yaml`. Default secret = client_id (e.g., `svc-ds-portal` / `svc-ds-portal`).

## Security posture

### Zero-trust internal APIs

Every endpoint authenticates a JWT bearer and authorizes it with one unified guard from the shared `libs/ds-auth` library (`from ds_auth.fastapi import require_permission`). There are no "internal-only" unprotected endpoints.

`require_permission("service.resource.action", ...)` authorizes **both** principal kinds against the same permission vocabulary:

- **Service tokens** (Keycloak client-credentials) authorize on their `scope` claim.
- **User tokens** (OIDC login) authorize on their Keycloak **groups** (realm-level `groups` + org-level `organization.<alias>.groups`, merged by `ds_auth.extract_groups`). Group names mirror the scope names.
- `{service}.admin` is a superset that satisfies any `{service}.*`.

This mirrors the `celine-sdk` claim semantics on purpose (a compatible *approach*, not a code dependency) so a Keycloak realm synced from `clients.yaml` by the shared `celine-policies` CLI authorizes identically across projects.

Verification is **fail-closed**: `ds_auth` verifies signature + audience + issuer via JWKS whenever an OIDC issuer is configured. Local dev without a reachable Keycloak requires the explicit, loud `*_OIDC_INSECURE_DEV=true` opt-in (default in dev settings); production sets the issuer, which enforces verification regardless.

Service clients and their scopes are defined in `services/keycloak/clients.yaml`; user groups live in the realm import (`services/keycloak/realm-*.json`) / are provisioned by the `celine-policies` CLI. The `keycloak-sync` init container provisions clients on startup.

When adding or modifying API endpoints:
- Define the required permission (`service.resource.action`) in `clients.yaml` (as a scope) so service tokens can hold it, and ensure the matching group exists for user access
- Add `Depends(require_permission("service.resource.action"))` (Python)
- Ensure the calling service's client has the scope in its `default_scopes`
- Never add unprotected endpoints that accept sensitive data or perform mutations

### Cross-checks on edits

When modifying any service, verify:
1. **Auth guards**: every new/changed endpoint uses `Depends(require_permission(...))` from `ds_auth`
2. **Scope/group alignment**: the calling service's KC client has the required scope in `clients.yaml`; user access has a matching group in the realm
3. **URL scheme**: new URLs use `172.17.0.1` (backend) or `*.dataspaces.localhost` (browser-facing), never raw `localhost`
4. **Idempotency**: bootstrap/provisioning operations remain safe to re-run
5. **Credential hygiene**: no hardcoded secrets outside dev-default settings; production must override via env vars