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
│   ├── caddy/                  Config — reverse proxy for portal, connector APIs, and Keycloak
│   └── keycloak/               Config — OIDC realm import for dev
├── libs/                       Importable shared Python packages (no Dockerfile, no port)
│   ├── governance/             ds-governance — GovernanceRuleV2, ODRL mapper, `ds-governance` CLI (import `ds.governance`)
│   ├── ds-auth/                ds-auth — JWT auth + unified scope/group authorization (import `ds_auth`)
│   ├── ds-edc/                 ds-edc — EDC Management API v3 client + Pydantic models (import `ds_edc`)
│   └── ds-e2e/                 ds-e2e — end-to-end verification framework (`ds-e2e` CLI)
├── docs/                       mkdocs site — architecture, deployment reference, blueprints
├── helm/                       Helm charts + helmfile for Kubernetes deployment
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

- **`libs/`** — a package with no `Dockerfile` and no port; consumed via an editable path dependency. Today: `libs/governance` (`ds-governance`, imported as `ds.governance`), `libs/ds-auth` (`ds-auth`, imported as `ds_auth`), and `libs/ds-edc` (`ds-edc`, imported as `ds_edc` — shared EDC Management API v3 client and Pydantic models).
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
  ├── DID documents      GET /dids/{did}/did.json (EDC resolves directly via identity-did-web)
  ├── STS tokens         POST /sts/{did}/token (ES256 SI JWTs)
  ├── Credential service POST /credentials/{did}/presentations/query (DCP VP queries)
  ├── Participant registry GET /admin/participants, GET /admin/participants/check?did=&scope=
  ├── Owners registry    GET /owners/resolve?alias=<name>, CRUD /admin/owners
  ├── Memberships        GET /memberships/check?user_did=&organization=, CRUD /admin/memberships
  ├── Org onboarding     /admin/organizations/applications, /admin/credentials/organization,
  │                      /admin/owners/{alias} (PATCH), /promote, /agreement  (Block D)
  ├── Agreements         GET /agreements, /agreements/{id}, /agreements/{id}/acceptances
  └── StatusList2021     GET /status/{list_id}

Federated Catalog (30003) ──→ identity-registry /participants (provider discovery)
ds-connector ──→ identity-registry /participants (HttpParticipantRegistry with TTL cache)
ds-connector ──→ identity-registry /owners/resolve (HttpOwnersRegistry with TTL cache)
ds-connector ──→ identity-registry /memberships/check (consent-time subject-pool validation)

dataset-api (30002, external) ──→ ds-connector /internal/*  agreement + consent checks
```

## Compose topology

Three compose files form the full stack:

| File | Services | Purpose |
|------|----------|---------|
| `docker-compose.yml` | caddy, postgres, identity-registry, keycloak, keycloak-sync, keycloak-org-sync | Shared infrastructure |
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
| Database | PostgreSQL 17.4 (one DB per service, all on port 35432; EDC uses SQL stores with Flyway auto-migration) |
| Proxy | Caddy 2 (HTTP reverse proxy for portal, connector APIs, and Keycloak) |
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
| 9080 | Keycloak |
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
1. EDC resolves `did:web:provider.dataspaces.localhost` using its `identity-did-web` module over HTTP (`edc.iam.did.web.use.https=false`)
2. `*.dataspaces.localhost` resolves to Caddy via Docker network aliases (defined on the caddy service in `docker-compose.yml`)
3. Caddy rewrites `GET /.well-known/did.json` → `GET /dids/did:web:{host}/did.json` and proxies to the identity-registry
4. The identity-registry builds and returns the DID document from its database

**When running EDC on the host** (`task edc-provider:run` / `task edc-consumer:run`), Docker network aliases are not available. Either add `*.dataspaces.localhost` entries to `/etc/hosts` and publish Caddy port 80, or rely on the `DemoIdentityFallbackExtension` (`ds.demo.identity.enabled=true` in EDC properties).

The `ir-cli` tool (installed in the identity-registry container) handles bootstrap and participant registration. See `task identity:bootstrap` for the full setup sequence.

## Deployment / production configuration

**See `helm/AGENTS.md` for the full deployment contract**, and `docs/deployment/` for the operator documentation (prerequisites, Keycloak realm contract, `values.yaml` reference, secrets, exposure, day-2 operations — published as the Deployment section of the docs site). The essentials:

### The `DS_ENV` production guard

Dev is zero-config on purpose. The safety net is a single environment switch.

Every Python service builds a `ProductionGuard` (`libs/ds-auth/src/ds_auth/production.py`) at startup and registers its dangerous defaults:

| `DS_ENV` | Behaviour |
|----------|-----------|
| unset / `dev` | Logs a warning per violation, starts normally |
| `production` | Logs **all** violations together and **refuses to start** |

The Helm chart must set `DS_ENV=production` on every service container.

**When you add a setting with a dev default, register it with the guard in the same change** — an unregistered insecure default is invisible to the chart.

### Env file roles

| File | Role |
|------|------|
| `.env.local` | Committed zero-config dev defaults. Makes `task start` and the e2e smoke tests work with no setup. Deliberately weak and public. |
| `.env.example` | The documented reference for **every** variable — purpose, blast radius, generation command. Not a working config; the model the Helm chart is built from. |
| `.env` | Per-machine overrides, gitignored. |

### Secret bootstrap

```bash
task secrets:bootstrap   # generate .env.production + EC P-256 keys, idempotent
task secrets:check       # fail if any dev default or CHANGE_ME remains
```

Both preserve existing values, so they are safe to re-run. `task secrets:check` belongs in the release pipeline.

### Non-Python surfaces the guard cannot reach

- **`DS_DEMO_IDENTITY_ENABLED`** — never set it in production. It makes the EDC accept self-issued DCP tokens *without signature verification*, bypassing DSP authentication entirely. Defaults to `false`; dev compose sets it `true` explicitly.
- **EDC vault properties** (`services/connector/config/*-vault.properties`) — zero-config dev fixtures containing placeholder EC keys and `insecure-dev-secret`, in the same category as `.env.local`. Production renders them from `task secrets:keygen` output via Kubernetes secrets.
- **`AUTH_SECRET`** (portal) — `hooks.server.ts` falls back to a literal when unset; the chart must always supply it.
- **Keycloak realm** — the dev realm has four users whose password equals their username and `directAccessGrantsEnabled: true`. Production must select `realm-production.example.json` and run `start --optimized`, not `start-dev`.
- **`IDENTITY_REGISTRY_ENCRYPTION_KEY`** — Fernet-encrypts all DID private keys at rest. Losing it makes them unrecoverable; back it up outside the cluster.

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

### Validating governance before import

`ds-governance` (the CLI shipped by `libs/governance`) gates a governance file **before**
`POST /provider/sync` pushes it into an EDC. It validates *input* — it deliberately does not
re-assert the mapper's output, which is covered by `libs/governance/tests/tests/test_mapper.py`:

- EDC asset/policy/contract id collisions between dataset keys (an import would silently clobber)
- referential integrity of `ownership[].name` against the owners registry, and owner DIDs
  against the participant registry
- coherence of a rule's own declarations (consent vs row filters, retention, validity window)
- `--deny-key <glob>` for keys that must not reach a given environment

```bash
task compliance:validate           # offline, against the YAML seeds
task compliance:validate:runtime   # against a running identity-registry
task compliance:evidence           # DCAT-AP catalog + ODRL offers → reports/compliance
```

Registries resolve either from YAML seeds (`--owners`, `--participants`) or from a live
deployment (`--identity-registry-url`), so the same gate runs in CI and against production.
Every deployment-specific value is a flag — `--participant-id`, `--base-url`,
`--participant-did`, `--profile`. **Pass `--participant-did` outside dev**: without it the
mapper's ODRL assigner fallback is `did:web:<participant-id>.dataspaces.localhost`.

### Ownership & owner resolution

Governance rules can declare an `ownership` block binding datasets to named organizations:

```yaml
defaults:
  ownership:
    - name: example-org
      type: DATA_OWNER
```

The **owners registry** lives in the identity-registry DB (`Owner` table), seeded by `ir-cli owner import --file owners.dev.yaml`. The connector resolves owner aliases at sync time via `HttpOwnersRegistry` (calls `GET /owners/resolve?alias=<name>`).

Resolution chain:
1. `governance.yaml` ownership alias → identity-registry `Owner` → `canonical_uri` (DID > URL)
2. ODRL assigner = resolved owner DID (falls back to participant DID if unresolved)
3. Membership constraint operand = `owner:<alias>:member` (for `internal`) or `owner:<alias>:partner`
4. Consent subject-pool: connector checks `GET /memberships/check` before creating consent records

**Governance overlay:** `governance.<name>.yaml` merges on top of the base file. Set `CONNECTOR_GOVERNANCE_OVERLAY_NAME` or pass `overlay_name`. `*.local.yaml` is gitignored for deployment-specific bindings.

### The consent vocabulary — purposes, sharing offers, the circle

Three vocabularies have to agree before a person can be asked anything meaningful:

```
purpose slug ──► ODRL profile taxonomy (SKOS, /ns/policy)
     │ groups                    dpv_mapping → DPV IRI (docs only)
     ▼                           broader     → local hierarchy (enforcement)
sharing offer ──► governance.yaml datasets (declare policy.purpose[])
     │ consented as
     ▼
consent row (dataset + purpose + controller-role, all validated)
     │ compared at
     ▼
GET /internal/consent/check?purpose=…&controller_role=…
```

| Rule | Why |
|---|---|
| `policy.purpose[]` is the **only** runtime source of a dataset's purposes | `tags` are DCAT-AP keywords — a topic is not a reason for processing. `tag_to_purpose` is an authoring default for scaffolding only |
| `odrl:isA` matching follows **only** the local `broader` chain, never `dpv_mapping` | A `broadMatch` to a generic DPV term would let an unrelated use satisfy a specific consent |
| Empty `purpose[]` is **never** a wildcard for personal data | The person was never told the use, so the consent fails GDPR Art. 4(11). Fail closed — this applies to the requested purpose too |
| Consent to a child purpose does **not** cover its parent | That would widen consent |
| The consent key is **(subject, purpose, controller-role)** | Controller ≠ legal entity: a DSO's grid-operations and metering functions are distinct controllers |
| Only `dpv:Consent` offers get a UI control | Contract-based processing is disclosed, not toggled; asking implies a choice that does not exist |
| A **covered processor** is disclosed, never asked | Same controller, same operation (Art. 28). `POST /consent/request` returns 409 |
| `user_visible_hash` excludes `datasets[]` | Which datasets back an offer is a schema-migration concern nobody was shown |

Sharing offers live in `services/connector/governance/sharing-offers.yaml` (same overlay mechanism as `governance.yaml`) and are served publicly at `GET /ns/sharing-offers` as **codes plus an English fallback** — translation is entirely the frontend's job, and dataset keys are not in the public projection.

Consent writes resolve through `services/connector/src/connector/services/consent_vocabulary.py`; anything outside the declared vocabulary is a **422**. `task compliance:validate` gates the whole chain before an import.

**Service-provisioned shares & the scoped wildcard.** The onboarding wizard records a subject's standing consent after approval via `POST /consent/admin/shares` (scope `connector.consent.provision` on `svc-ds-onboarding`). It names an `offer_id`, not a dataset; the connector expands it into `consumer_id = "*"` rows — the **scoped wildcard**, which admits any party inside the circle for that controller and purpose (never a new controller or purpose). A per-party specific row overrides the wildcard: an explicit grant or opt-out both win. Each row carries a `legal_basis` evidence record (DPV basis IRI, consent-text version, locale, rendered-text SHA-256, `user_visible_hash`, `submission_ref` — **codes and hashes only, never PII**), surfaced on `GET /consent/my`, `/consent/status` and `/internal/consent/check`.

See `docs/consent-and-sovereignty.md` for the full model and the enforcement matrix.

**Consent & disclosure provenance (Block C).** The connector emits four PROV-O
events to ds-provenance: `ConsentGranted` / `ConsentRevoked` (on grant/revoke,
from the API layer after commit), `DataIngested` (an operator records a manual
DSO handover via `POST /admin/ingestion`, guard `connector.ingestion.record`),
and `DataDisclosed` (the onboarding CSV export, when a `--recipient` is named,
using `svc-ds-onboarding`'s `provenance.write` scope). All four carry **codes,
pseudonymous DIDs and hashes only — never PII**: a `consent_snapshot_hash` (a
recomputable SHA-256 over the authorising consent tuples) proves *which* consent
state backed a handover without the provenance store holding subject data. See
`docs/provenance-and-lineage.md`.

### Organization memberships

The `OrganizationMembership` table in identity-registry tracks which user DIDs belong to which owner organizations. Seeded by `ir-cli membership add` or `ir-cli membership import --community-registry`.

The connector's consent endpoint checks membership before accepting consent requests for datasets with ownership. The portal reads KC JWT claims for UX; data access decisions always go through the IR API.

### KC organizations (portal UX gating)

Keycloak native organizations (KC 24+ feature) provide portal-level gating parallel to IR memberships. Configured in `services/keycloak/organizations.yaml` and provisioned by `ir-cli keycloak org-sync` (runs as the `keycloak-org-sync` init container). The `organization` client scope with `oidc-organization-membership-mapper` in the dev realm maps org memberships to JWT claims (`organization.<alias>.groups`). The portal extracts org membership from JWTs to gate provider actions (sync, asset management) per-owner.

## Quick start

```bash
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
| Roadmap & deferred work | `docs/roadmap.md` |
| Consent & sovereignty | `docs/consent-and-sovereignty.md` |
| Owner identity & ownership | `docs/owner-identity-and-ownership.md` |
| DSSC Blueprint reference | `docs/dssc-blueprint-docs/` |
| Per-service guides | `services/*/AGENTS.md` and `services/*/README.md` |

## Common agent tasks

| Task | Where to start |
|------|---------------|
| Add a new dataset to the catalogue | `services/connector/governance/governance.yaml` |
| Add or change a sharing offer | `services/connector/governance/sharing-offers.yaml`, then `task compliance:validate` |
| Add a purpose to the taxonomy | `libs/governance/src/ds/governance/profiles/energy.yaml` |
| Add a new ODRL constraint type | `libs/governance/` (mapper) + `services/edc-extensions/` (function, **plus a rule binding**) |
| Add a new API endpoint to connector | `services/connector/src/connector/api/v1/` |
| Add a new portal page | `services/portal/src/routes/` |
| Add a new provenance event type | `services/provenance/src/provenance/schemas/events.py` + `services/connector/src/connector/services/prov_bridge.py` |
| Change consent behavior | `services/connector/src/connector/services/consent_service.py` |
| Add a new participant | `task identity:bootstrap` or `ir-cli participant add` in the identity-registry container |
| Add/manage owners | `ir-cli owner add/list/import/remove` or `POST /admin/owners` |
| Add/manage memberships | `ir-cli membership add/list/import/remove` or `POST /admin/memberships` |
| Onboard an organisation | `ir-cli org register/verify/agreement/issue-credential/promote` or `/admin/organizations/*` (Block D) |
| Add/change a service agreement | `services/identity-registry/seed/agreements.dev.yaml` + `seed/content/*.md`, then `ir-cli agreement import` |
| Add/manage KC organizations | `services/keycloak/organizations.yaml` + `ir-cli keycloak org-sync` |
| Add identity-registry API endpoints | `services/identity-registry/src/identity_registry/api/v1/` |
| Modify EDC connector build | `services/edc-connector/build.gradle.kts` |
| Issue a new credential type | `services/identity-registry/src/identity_registry/services/vc.py` + `admin.py` (or `organizations.py` for org credentials) |

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

### Three authentication mechanisms — know which one applies

Most endpoints use the unified `ds_auth` guard, but **two other mechanisms exist**. Using the wrong one when adding an endpoint is the most common security mistake in this repo.

| Mechanism | Where | How it authenticates |
|-----------|-------|----------------------|
| **`require_permission`** (default) | Everything except the two below | JWT bearer → scope (service) or groups (user) |
| **`X-Api-Key`** | `/internal/*` on ds-connector | Static shared secret equal to `EDC_API_KEY`, used by the Java EDC extensions and dataset-api. See `connector/dependencies.py`. |
| **VC-JWT headers** | `/consent/*` and `/consumer/*` on ds-connector | `X-Subject-Id` + `X-User-VC`, verified against the trust-anchor key by `services/user_credentials.py`. **Not** `require_permission`. |

The DCP-facing identity-registry endpoints are a fourth case: `/sts/{did}/token` authenticates with the participant's STS client secret, and `/credentials/{did}/presentations/query` requires a self-issued DCP token signed by the requested DID's registered key.

Public by design: `/dids/`, `/status/`, `/health`, and the connector's `/ns/policy` and `/ns/sharing-offers` static vocabularies. Both are vocabularies rather than data — an onboarding wizard has to render offers before anyone has an identity — and the offer projection deliberately omits dataset keys.

> `/metrics` on ds-connector, ds-provenance, ds-federated-catalog and dataset-api is currently **unauthenticated** and reachable through Caddy. Treat it as a known gap, not a pattern to copy.

### Zero-trust internal APIs

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