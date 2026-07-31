# ds — Agent Guide

Root guide. Load this plus the `AGENTS.md` of whatever you are working on
(`services/<name>/`, `libs/<name>/`, `helm/`). 

Consult .agents/facts as you load AGENTS.md, the facts structure is parallel to repository structure (eg .agents/facts/services/connector.md and facts.md map for repo wise details)

Nothing else is required reading.


## What this repository is

A DSSC-Blueprint-aligned dataspace platform, specialised for energy communities via
CEEDS. It implements the consumer-pull exchange end to end: catalogue discovery,
ODRL contract negotiation, EDR-gated transfer, consent-based row filtering, and
PROV-O provenance.

**It is a platform, not a deployment.** Keep it generalisable — domain specifics belong
in extension points (the ODRL profile, governance overlays, Keycloak client overlays),
never in platform code.

### Publishing boundary — this repo is open source

Do not commit, in code, docs, tests, fixtures or dev defaults:

- names of real organisations, people, sites or customers
- real dataset names, table names or identifiers from a deployment
- private project or repository references beyond the integration facts in
  [Relation to celine](#relation-to-celine)

Dev fixtures use `example-org`, `grid-operator`, `*@example.test`, `*.dataspaces.localhost`.
Keep it that way. When a real deployment needs a real binding, it goes in a gitignored
overlay (`*.local.yaml`, `.env`, `taskfile.local.yaml`).

### What is documented where

| Question | Source |
|---|---|
| How do I work on this unit? | this file + the unit's `AGENTS.md` |
| **What must a dataspace implement?** | **`docs/blueprints/`** — DSSC v3.0 and CEEDS v3.0, rendered as citable requirements. **This is the requirements source for the whole platform** |
| What has this dataspace decided? | `docs/rulebook/` — the recorded decisions, each with an enforcement status |
| What does the code currently do? | `docs/services/*` — one page per unit: its role, how it works, its configuration reference |
| How is it built and run? | `docs/development/*` |
| How is it deployed? | `docs/deployment/*` — prerequisites, the realm contract, `values.yaml`, secrets, exposure, day-2 operations |
| What is broken? | `.agents/defects.md` (by theme), `.agents/defect-per-service.md` (by unit) |

**Requirements come from the blueprints.** `docs/blueprints/dssc/` carries the obligations;
`docs/blueprints/ceeds/` carries the energy-domain bindings; `docs/blueprints/comparison.md`
reconciles them. Every unit's `AGENTS.md` links to the building block it implements. Read the
building block before changing behaviour in the unit that implements it.

### How to use `AGENTS.md` and `docs/` together

`AGENTS.md` files are **navigation and constraints only**. They do not restate what is in
`docs/`, and they are not the place to learn how something works.

**Read `docs/` on demand**, when you need something that cannot be derived from the code or
obtained from the user: a requirement, a cross-cutting architectural decision, why a rule
exists, what a counterparty expects. Do not read the docs tree speculatively — each unit's
guide names the two or three pages that matter for it.

**Propose deviations; do not take them.** If the code must depart from a blueprint
requirement, a rulebook rule, or the conventions in this file, say so, state the reason and
the alternative, and get agreement before implementing. Record what was agreed in
`docs/rulebook/scope-and-deviations.md`. An undeclared deviation is indistinguishable from a
defect, which is exactly how the current ledger got as long as it is.

## Relation to celine

`ds` is the dataspace layer; **celine** is the domain platform deployed with it. Four
integration points, and no others:

| Point | What crosses |
|---|---|
| **Data plane** | celine `dataset-api` is the real data-plane interface. `ds` addresses it as an HTTP endpoint and calls it back at `POST /internal/dataplane/authorize` |
| **Realm sync** | `celine-policies` CLI applies `services/keycloak/clients.effective.yaml` to a Keycloak realm |
| **Governance schemas** | `governance.yaml` (dataset definitions) and `owners.yaml` (organisation definitions) are shared shapes. `ds` publishes the ones it defines under `schemas/`; `governance.schema.json` is defined on the celine side and cached here |
| **Dev workspace** | `docker-compose.dataset-api.yml` builds sibling checkouts. Paths are `.env` overrides (`DATASET_API_PATH`, `REC_REGISTRY_PATH`, `CELINE_SDK_PATH`); no layout is baked in |

celine services read their OIDC client from `CELINE_OIDC_*`, not `OIDC_*`.

## Repository structure

```
services/     deployable units — Dockerfile + port. One AGENTS.md each
libs/         importable Python packages — no Dockerfile, no port. Editable path deps
helm/         Kubernetes charts + helmfile. See helm/AGENTS.md
schemas/      JSON Schema for YAML shapes that cross a repo boundary (generated)
docs/         mkdocs site — services, rulebook, blueprints, development
.agents/      working documents: defect ledger, analyses, plans (gitignored)
```

| Unit | Role |
|---|---|
| `services/connector` | Control plane beside the EDC: governance sync, consent registry, `/internal/*` PDP, consumer-side DSP driver |
| `services/identity-registry` | Trust anchor: DIDs, VCs, STS, DCP credential service, participant/owner/membership registries, org onboarding |
| `services/portal` | SvelteKit UI for every role. SSR only, not an OIDC client |
| `services/provenance` | PROV-O graph and lineage, one instance per participant |
| `services/federated-catalog` | Crawls participants, republishes the union as one DCAT catalogue. Advisory index, never authority |
| `services/edc-extensions` | Java: ODRL constraint functions, pending guard, negotiation resume, event publisher |
| `services/edc-connector` | Gradle fat-JAR build of the EDC runtime. No source of its own |
| `services/dataset-api-mock` | Stand-in for the celine dataset-api. See [Data plane](#the-data-plane) |
| `services/dataset-api-fiware-adapter` | FIWARE/QuantumLeap plugin for the host dataset-api. Currently unwired |
| `services/caddy` | Dev edge: DID resolution, `/api/*` fan-out, the auth wall |
| `services/keycloak` | Realm contract: permission vocabulary, clients, organizations, realm imports |
| `services/oauth2-proxy` | Browser session holder. Caddy `forward_auth` target |
| `libs/governance` | `ds-governance` — governance/offer models, ODRL mapper, validation CLI |
| `libs/ds-auth` | `ds_auth` — JWT verification, principals, role bundles, `require_permission` |
| `libs/ds-edc` | `ds_edc` — EDC Management API v3 client and models |
| `libs/ds-e2e` | `ds-e2e` CLI — live end-to-end flows against a running stack |

New shared code goes in `libs/`, never under `services/`. To depend on one: add it to
`pyproject.toml` `[project].dependencies`, point `[tool.uv.sources]` at the path, and in
the Dockerfile `COPY libs/<lib>/` then `uv pip install` it before the service.

## How the services talk

```
Portal ──▶ connector (provider 30001 / consumer 31001) ──▶ EDC Management API
                    ├──▶ provenance (30000 / 31000)
                    └──▶ federated-catalog (30003)

EDC provider ◀──DSP──▶ EDC consumer
  ├──▶ identity-registry   STS tokens, DCP presentation queries, did:web
  └──▶ connector /internal/*   ODRL constraint evaluation

dataset-api ──▶ connector /internal/dataplane/authorize   per-query decision + row filter
connector, federated-catalog ──▶ identity-registry   participants, owners, memberships
```

### Ports

| Port | Unit | | Port | Unit |
|---|---|---|---|---|
| 30000 / 31000 | provenance (provider / consumer) | | 9080 | Keycloak |
| 30001 / 31001 | connector (provider / consumer) | | 80 | Caddy gateway (all hosts) |
| 30002 | dataset-api (real, or the mock) | | 19xxx / 29xxx | EDC provider / consumer |
| 30003 | federated-catalog | | 35432 | PostgreSQL (one DB per service) |
| 30004 | portal | | 30022 | dataset-api mock, when the real one holds 30002 |
| 30005 | identity-registry | | 309xx / 319xx | debugpy |

### Host binding — the rule that makes local and Docker interchangeable

| Direction | Address |
|---|---|
| Browser-facing, OIDC issuer, `ORIGIN`, callbacks | `*.dataspaces.localhost` through Caddy on `:80` — portless, split by Host header |
| Any backend call, host↔container in either direction | `172.17.0.1:<port>` |
| Container-to-container inside one compose stack | Docker DNS service name |

**Never `localhost:<port>` for a service URL.** `172.17.0.1` is the Docker host gateway and
resolves identically from the host and from a container, which is the whole reason a service
can be stopped in Docker and restarted on the host without anything else changing.

## The data plane

**The real data plane is the celine `dataset-api`.** It owns the query surface
(`POST /query` with `{sql, limit, offset, skip_count}`), and it is the policy enforcement
point: it verifies the EDR bearer, calls `POST /internal/dataplane/authorize`, applies the
returned row filter, and emits a query-audit event.

`services/dataset-api-mock` is a **stand-in**, and that has two consequences:

- **Exclude it from assessments.** It is not a deployed component. Its defects are only
  interesting where they reveal a contract mismatch.
- **Keep it aligned anyway.** It mirrors the real signature deliberately. A flow that
  passes only against the mock is evidence about an API nobody runs — so when the
  connector's `/internal/*` contract changes, the mock changes with it, in the same commit.

`./services/dataset-api-mock/fixtures/seed.sh` swaps the real dataset-api onto 30002 and
moves the mock to 30022, so `task e2e:all` and the UI tests can run against the real thing.

## Environment

| File | Role |
|---|---|
| `.env.example` | **The reference.** Every variable the platform reads, with purpose and blast radius. Not a working config |
| `.env.local` | Committed zero-config dev defaults. Makes `task start` work with no setup. Deliberately weak and public |
| `.env` | Per-machine overrides. Gitignored |

Adding a setting means adding it to `.env.example` in the same commit. A variable that
exists in code and not there is invisible to anyone configuring a deployment.

Dev is zero-config on purpose; the safety net is `DS_ENV`. Every Python service builds a
`ProductionGuard` (`libs/ds-auth/src/ds_auth/production.py`) and registers its dangerous
defaults — under `DS_ENV=production` it logs all violations and refuses to start.
**Register a new dev default with the guard in the same change**, or the chart cannot see it.

## Running it

```bash
task start                 # infra → identity bootstrap → provider → consumer
task docker:restart        # everything in containers (slow, exercises Dockerfiles + compose env)
task dev:restart           # containers up, then hot-reload services in a tmux session `ds`
task status                # running containers
```

Both restart families take `BUILD=false` to reuse images.

**Ask which mode before restarting.** `dev:*` replaces ~12 services with host processes that
read `.env.local` through the Taskfile's `dotenv` and never see the compose `environment:`
block — so a change to a `Dockerfile`, a compose env block, a `pyproject.toml` dependency or
`build.gradle.kts` is **not verified** by `dev:*`. Usual sequence for a substantial change:
`dev:restart` to find logic bugs cheaply, then `docker:restart` to prove the container path.

`docker compose up -d` returns success even when an init container exited non-zero. After a
restart, check `docker ps -a` for non-zero `Exited` init containers before trusting a result.

### Dev users

All passwords equal the username. Realm `dataspaces`.

| User | Bundle / role | For |
|---|---|---|
| `admin@example.test` | `ds-admin` | platform admin |
| `provider@example.test` | `ds-participant-admin`, realm **and** org-scoped | dataset provider; exercises both provisioning paths |
| `consumer@example.test` | `ds-member` + `ConsumerUser` VC | data consumer |
| `subject@example.test` | `ds-member` + `DataSubject` VC | consent management |
| `dual@example.test` | both VC roles | proves roles are additive, not exclusive |
| `gridops@example.test` | `ds-participant-admin` **org-scoped only** (`grid-operator`) | proves a cross-owner write is refused |

Service accounts are in `services/keycloak/clients.yaml`; the dev secret equals the client id.

## Testing

Four layers. Each proves something the others cannot.

| Layer | Command | Proves |
|---|---|---|
| **Unit** | `task -d <unit> test` | logic, in isolation. Mandatory for every change |
| **Local stack** | `task dev:restart` | the code works against real dependencies, with hot reload |
| **Docker e2e** | `task docker:restart` then `task e2e:all` | the images, compose env and startup order work — **this must pass before e2e means anything** |
| **Portal UI** | `task -d services/portal test:ui` | Playwright journeys against the running stack |

The host-binding rule above is what makes layers 2 and 3 interchangeable: `ds-e2e` and
Playwright address `172.17.0.1` and the Caddy domains, so they neither know nor care whether
a given service is a container or a host process.

**Read the database directly when a result is ambiguous.** One Postgres on 35432, one
database per service, `postgres`/`postgres` in dev:

```bash
psql -h 172.17.0.1 -p 35432 -U postgres -l                    # list service databases
psql -h 172.17.0.1 -p 35432 -U postgres -d connector -c '…'   # inspect state precisely
```

An assertion about consent, agreement or provenance state is worth more when it is checked
against the row than against an API response.

## Taskfile

`Taskfile.yml` at the root is the only entry point a person should need. Namespaces:
`infra:*`, `provider:*`, `consumer:*`, `db:*`, `edc:*`, `e2e:*`, `keycloak:*`, `secrets:*`,
`compliance:*`, `docs:*`, plus the `docker:*` / `dev:*` lifecycle pairs. Per-unit Taskfiles
(`task -d <unit> <task>`) carry `setup`, `run`, `test`, `lint`.

**Keep it aligned as commands change.** A task is the documented way to do a thing; a command
in a doc that is not a task will be wrong within a month. When you change how something is
run, change the task — do not add a second way.

`taskfile.local.yaml` is included when present (`optional: true`, `flatten: true`) and is
gitignored. It is where deployment-local commands live — anything referencing paths outside
this repo. `taskfile.local.example.yaml` is the committed template.

## Code style

**Every change carries unit tests and passes lint.** Not negotiable, and not "later" —
the repository already has six tests failing on `main` and two libraries whose linters are
configured and invoked by nothing.

### Python (3.12)

- FastAPI, async throughout. `httpx.AsyncClient`, never `requests`
- `pydantic-settings` for config; defaults work for local dev, overridden by env
- Layout: `src/<pkg>/{main,config,dependencies}.py` + `api/`, `services/`, `clients/`, `db/`, `schemas/`
- Async SQLAlchemy. **Sessions auto-begin** — never call `session.begin()` inside
  `async with factory() as session:`; do the work and `await session.commit()`
- Alembic: `task db:revision MESSAGE=...`, `task db:migrate`
- `uv` for dependencies. Services install as packages (`uv pip install .`) so console
  scripts exist in the image
- `ruff`, `mypy`, `pytest` + `pytest-asyncio`, `respx` for HTTP mocking

### TypeScript / Svelte

- SvelteKit 2, Svelte 5 runes (`$state`, `$derived`, `$effect`) — not Svelte 4 stores
- SSR: upstream calls in `+page.server.ts`, never from a browser component
- Mobile-first Tailwind
- Route guards in `src/lib/server/auth.ts`. **A `+server.ts` endpoint does not run
  `+layout.server.ts`** — guard it itself
- Playwright journey for any new user-facing flow

### Java (21)

- EDC SPI interfaces; `Monitor` for logging
- Gradle + Shadow. `task edc:build`, `task edc:restart`
- A constraint function must **deny on error**. Returning `true` when an input is missing or
  a call fails is the defect class this codebase has the most of

### Security, on every change

1. Every new or changed endpoint carries `Depends(require_permission("service.resource.action"))`
2. The permission exists in `services/keycloak/clients.yaml` (then `task keycloak:merge`,
   `task keycloak:mirror`) and in a bundle in `libs/ds-auth/src/ds_auth/bundles.py`
   (then `task auth:bundles:generate`). A scope in neither a bundle nor
   `SERVICE_ONLY_PERMISSIONS` fails `libs/ds-auth/tests/test_vocabulary.py` — deliberately
3. Never a machine-identity permission in a human bundle
4. New URLs use `172.17.0.1` or a Caddy domain, never raw `localhost`
5. Bootstrap and provisioning stay idempotent
6. No hardcoded secrets outside dev defaults registered with `ProductionGuard`

There are **two** authentication mechanisms and using the wrong one is the commonest
mistake here: `require_permission` (JWT → scope for services, expanded groups for users)
everywhere, and VC-JWT headers (`X-Subject-Id` + `X-User-VC`) on the subject-facing routes
(`/consent/my/*`, `/consent/status`, `/consumer/*` on the connector). See `libs/ds-auth/AGENTS.md`.

## Maintaining these files

The point of an `AGENTS.md` is to get an agent to the right file quickly and stop it making
a wrong edit. It is not a design document.

**Every unit guide opens with a `## References` block** naming the blueprint building block
it implements, the rulebook page that states its rules, and its `docs/services` page. That
block is the unit's entry into the requirements; keep it accurate and keep it short.

**Include:** the unit's role and boundary · where things live · which files to touch for
common tasks · constraints that are not visible from the code · the specific traps that
have caused wrong edits here.

**Exclude:** full source-tree listings (the tree is the tree) · route and env inventories
(`docs/services/*` regenerates them; `.env.example` owns variables) · behaviour narration
and design rationale (`docs/`) · anything already asserted by a test · history of what broke
and when (`.agents/defects.md`, git log).

**Rules:**

- One fact, one home. If it belongs in `docs/`, link to it — a duplicated fact becomes two
  contradicting facts.
- Prefer a pointer to a prose explanation: `see services/connector/src/connector/services/consent_service.py`
  beats three paragraphs describing it.
- Do not restate the root guide in a sub-guide.
- Delete on sight. A stale instruction is worse than a missing one, because it is followed.
- Update the guide in the same commit as the change that dates it.
- Do not clutter AGENTS.md with transient details, until those are structurally part of the repo. Store in .agents/facts/*.md relevant details, use the same repo folder structure eg (services/connector.md, or libs/ds-auth.md, facts.md for repo wise details). 

Every unit under `services/` and `libs/` should have one. If one is missing, say so.
