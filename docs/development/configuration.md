# Configuration

How a setting gets from a file into a running process, and where to look for the name of one.

**`.env.example` at the repository root is the reference.** It lists every variable the
platform reads, what it does, and its blast radius if leaked. This page explains the mechanics;
that file is the catalogue, and per-service tables live on each service page.

## The three env files

| File | Role |
|---|---|
| `.env.example` | **the reference.** Not a working config |
| `.env.local` | committed zero-config dev defaults. Makes `task start` work with no setup. Deliberately weak and public |
| `.env` | per-machine overrides. Gitignored, absent by default |

Adding a setting means adding it to `.env.example` in the same change. A variable that exists
in code and not there is invisible to anyone configuring a deployment.

## How they reach a process

Two mechanisms, and only one of them actually does anything.

**Task's `dotenv`** loads `.env` then `.env.local` and exports the result into every task's
environment. This is what delivers values to host processes *and* to compose variable
substitution. First file wins, and an already-set OS variable beats both.

**pydantic-settings' `env_file`** is declared by every settings class, but it resolves
**relative to the process working directory** — and no service is ever started from a directory
containing a `.env`. In practice no settings class ever loads a dotenv file itself.

For the provider and consumer stacks, compose is invoked with an explicit
`--env-file .env.local`, which *replaces* compose's default `.env` lookup. The shared infra
stack relies on Task's exported environment instead. Running `docker compose up -d` by hand
therefore reads neither file and falls back to the `${VAR:-default}` values written into the
compose files.

## How a variable is named

Five mechanisms, none interchangeable.

### 1. A prefix per service

| Service | Prefix |
|---|---|
| ds-connector | `CONNECTOR_` |
| identity-registry | `IDENTITY_REGISTRY_` |
| ds-provenance | `PROVENANCE_` |
| ds-federated-catalog | **`CATALOG_`** |
| dataset-api-mock | **`DATASET_API_`** |
| ds-e2e | *(none — bare names)* |

Three of the six do not use the service's own name. `CATALOG_MAX_DATASETS_PER_PROVIDER` is
correct; `FEDERATED_CATALOG_…` is read by nothing.

### 2. An alias overrides the prefix entirely

A field carrying an explicit alias is read under **that literal name**, prefix discarded. The
connector's six `EDC_*` variables and the identity registry's eight `KEYCLOAK_*` variables work
this way.

### 3. Whether the prefixed form *also* works

| Service | Prefixed form accepted? |
|---|---|
| ds-connector, ds-federated-catalog | **yes** — both names work; the alias wins when both are set |
| identity-registry, ds-provenance, dataset-api-mock | **no** — only the alias works. `IDENTITY_REGISTRY_KEYCLOAK_ADMIN_URL` is read by nothing |

### 4. The portal has no prefix machinery at all

SvelteKit exposes the process environment verbatim. No settings class, no schema — an unset
variable is `undefined` and each call site supplies its own fallback, so the same variable can
have different effective defaults in different routes.

### 5. The EDC converts `ENVIRONMENT_NOTATION` to `dot.notation`

`DS_CONNECTOR_INTERNAL_CLIENT_ID` arrives as `ds.connector.internal.client.id`. The
`.properties` files **cannot** carry these values: the EDC's file loader does a plain
`Properties.load()` with no interpolation, so a `${VAR}` written there is stored verbatim. Every
secret-bearing EDC setting comes from the environment. See
[edc-connector](../services/edc-connector.md#how-settings-resolve).

## `DS_ENV` — the production guard

One variable, read in one place, defaulting to `dev`.

| Value | Behaviour |
|---|---|
| `production` | every registered violation is collected and the service **refuses to start**, listing all of them |
| anything else | the same violations are logged as one warning; startup proceeds |

Only the literal string `production` enforces. `prod` and `staging` behave as dev.

This is the mechanism that makes zero-config dev safe: every service registers its own dangerous
defaults at boot, so a chart author gets the complete list from one failed deploy.

What each service registers:

| Service | Refuses to start when |
|---|---|
| ds-connector | the OIDC issuer or the trust-anchor key path is unset; `OIDC_INSECURE_DEV` or `VC_INSECURE_DEV` is true; the EDC API key or the service secret is still at its dev default; a configured ODRL profile path does not exist |
| identity-registry | the OIDC issuer is unset; `OIDC_INSECURE_DEV` is true; the encryption key or the Keycloak client secret is still at its dev default; the realm admin password is a dev default **while** `KEYCLOAK_MUTATE` is on |
| ds-provenance | the OIDC issuer or the trust-anchor key path is unset; either `*_INSECURE_DEV` flag is true |
| ds-federated-catalog | the OIDC issuer is unset; `OIDC_INSECURE_DEV` is true; the service secret is still at its dev default |
| dataset-api-mock | the service secret is still at its dev default; EDR verification is off |

Beyond the per-service defaults, a set of values is refused **unconditionally**, registered or
not: empty, `admin`, `changeme`, `change-me`, `password`, `postgres`, `secret`, `test`.

**Register a new dev default with the guard in the same change that introduces it**, or the
deployment cannot see it.

## Where each kind of setting lives

| Kind | Where | Notes |
|---|---|---|
| Per-service application settings | the settings class, documented on that service's page | prefixed |
| The production switch | `DS_ENV` | un-prefixed, one value for the whole process |
| Schema-check bypass | `DB_SKIP_SCHEMA_CHECK` | un-prefixed and shared by all three Alembic services at once |
| EDC runtime settings | `services/connector/config/{provider,consumer}.properties` plus environment for secrets | see [edc-connector](../services/edc-connector.md) |
| Governance and offers | `services/connector/governance/*.yaml` | data, not environment |
| The realm contract | `services/keycloak/clients.yaml` and its overlays | data, not environment |
| Orchestration-only values | compose interpolation and Taskfile shell | no ds source file reads them |

### Orchestration-only variables

These are consumed by compose, Task or the client declaration — never by application code:

| Variable | Effect |
|---|---|
| `COMPOSE_PROJECT_NAME` | the compose project namespace (`dataspaces`) |
| `SVC_*_ID` / `SVC_*_SECRET` | fill both the realm client declaration and the service's own credentials |
| `KEYCLOAK_ADMIN_USERNAME` / `_PASSWORD` | the Keycloak container's bootstrap admin |
| `KEYCLOAK_TOKEN_URL` | fanned out into each service's own token-URL variable |
| `EDC_API_KEY` | the EDC's enforced Management API key, and the connector's copy of it |
| `DATASET_API_MOCK_PORT` | the mock's host port (`30022` by default, leaving `30002` to the real service) |
| `DATASET_API_PATH`, `REC_REGISTRY_PATH`, `CELINE_SDK_PATH` | sibling checkout locations for the real dataset-api stack |
| `CONNECTOR_DATABASE_URL_PROVIDER` / `_CONSUMER`, `PROVENANCE_DATABASE_URL_*`, `CONNECTOR_PROVENANCE_URL_*` | expanded by the per-role run tasks into the un-suffixed variable each service actually reads |

## Group aliases — mapping a foreign realm

If a Keycloak realm cannot use ds's five group names, do not rename anything. Each service
accepts `*_OIDC_GROUP_ALIASES` — a JSON map of foreign group name → ds **bundle** name. An alias
may only ever name a bundle, never a raw capability; anything else is dropped and logged.

The same idea applies to organisations: `CONNECTOR_OWNER_ALIASES` maps a foreign organisation
alias onto a ds owner id.

Both must be set on **every** service that reads them. A group map wired into some services and
not others is a deployment where a caller's authority depends on which service answered.

## Reproducing a settings table

Every per-service table in these docs comes from the settings class itself, never from an env
file. To regenerate one:

```sh
cd services/connector && uv run python -c "
from connector.config import Settings as S
p = S.model_config.get('env_prefix', '')
for n, f in S.model_fields.items():
    print(str(f.validation_alias) if f.validation_alias else (p + n).upper(), repr(f.default), sep='\t')
"
```

Substitute the module path for the other services: `identity_registry.config:Settings`,
`provenance.config:Settings`, `federated_catalog.config:Settings`,
`dataset_api_mock.main:Settings`, `ds_e2e.config:E2ESettings`.

**A variable documented under a name no code reads fails silently.** That command is how to
check.
