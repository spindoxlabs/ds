# Compose topology

Four compose files at the repository root. Three of them make one stack; the fourth is separate
and started by hand.

| File | Holds | Driven by |
|---|---|---|
| `docker-compose.yml` | shared infrastructure: the edge, the database, Keycloak, the identity registry | `task infra:start` |
| `docker-compose.provider.yml` | the provider participant | `task provider:start` |
| `docker-compose.consumer.yml` | the consumer participant | `task consumer:start` |
| `docker-compose.dataset-api.yml` | the **real** dataset API and REC registry, built from sibling checkouts | **no task** — run by hand |

The first three share the compose project `dataspaces`, so their containers are named
`dataspaces-<service>-1` and a `down` on any of them can reach all three. The fourth declares
its own project and is untouched by the lifecycle tasks.

## What runs where

### Shared infrastructure

| Service | Image | Published |
|---|---|---|
| `caddy` | `caddy:2-alpine` | `80:80` |
| `postgres` | `postgres:17.4-alpine` | `35432:5432` |
| `keycloak` | `quay.io/keycloak/keycloak` | `9080:9080` |
| `identity-registry` | built from `services/identity-registry` | `30005:30005` |
| `oauth2-proxy` | `quay.io/oauth2-proxy/oauth2-proxy` | **none** — reachable only as `oauth2-proxy:4180` |

Plus five one-shots: `identity-registry-db-create`, `identity-registry-db-init`,
`identity-registry-bootstrap`, `keycloak-sync`, `keycloak-org-sync`.

### Provider

| Service | Published |
|---|---|
| `edc-provider` | `19193` management, `19194` protocol, `19195`, `19291` |
| `ds-connector-provider` | `30001` |
| `ds-provenance-provider` | `30000` |
| `dataset-api-provider` (the mock) | `${DATASET_API_MOCK_PORT:-30002}:30002` |
| `ds-federated-catalog-provider` | `30003` |
| `ds-portal` | `30004` |

### Consumer

The provider file mirrored, minus the dataset API, the portal and the catalogue, with every
port shifted by +10000: `edc-consumer` on `29193`/`29194`, `ds-connector-consumer` on `31001`,
`ds-provenance-consumer` on `31000`.

The consumer stack overrides each Python service's `command` to move it onto its 31xxx port —
the images bake the provider-side ports.

## Startup graph

```
caddy ──────────────┐
postgres (healthy)  │
   └─ identity-registry-db-create → -db-init → identity-registry (healthy)
                                                  └─ identity-registry-bootstrap
keycloak (healthy) ─┼─ oauth2-proxy          (also waits on caddy having started)
                    └─ keycloak-sync → keycloak-org-sync
```

```
edc-<role>-db-create → edc-<role> (healthy) ─────────────┐
connector-db-create → connector-db-init ─────────────────┤
provenance-db-create → provenance-db-init                │
     └─ ds-provenance-<role> (healthy) ──────────────────┘
          └─ ds-connector-<role> (healthy)
               ├─ dataset-api-provider
               ├─ ds-portal
               └─ ds-federated-catalog-provider
```

The Keycloak branch and the identity-registry branch have no ordering edge between them; they
start concurrently.

The provider and consumer `*-db-create` one-shots **cannot** declare a dependency on `postgres`
— it lives in another compose file — so they poll `pg_isready` in their own command instead.

## The addressing convention

Almost every inter-service URL in the compose files is `http://172.17.0.1:<port>` — the Docker
host gateway, reached through the published port — rather than a compose service name. That
includes the database URLs, even for containers sitting on the same network as `postgres`.

This is the rule that makes the two run modes interchangeable:

| Direction | Address |
|---|---|
| Browser-facing, OIDC issuer, `ORIGIN`, callbacks | `*.dataspaces.localhost` through Caddy |
| Any backend call, host↔container in either direction | `172.17.0.1:<port>` |
| Container-to-container inside one stack | the Docker DNS service name |

**Never `localhost:<port>` for a service URL.** `172.17.0.1` resolves identically from the host
and from a container, which is the whole reason a service can be stopped in Docker and
restarted on the host without anything else changing.

The exceptions that *do* use container DNS are deliberate and few: the portal's upstream URLs,
Caddy's two DID routes and its oauth2-proxy routes, and the identity bootstrap's credential
service URL.

## The network

`docker-compose.yml` owns the `dataspaces` bridge network; the provider and consumer files
declare it `external: true`. So the root file must be up before either of them, and the root
`down` is what removes it.

Caddy carries seven **network aliases** on that network:

```
provider.dataspaces.localhost      consumer.dataspaces.localhost
trust-anchor.dataspaces.localhost  users.dataspaces.localhost
keycloak.dataspaces.localhost      sso.dataspaces.localhost
portal.dataspaces.localhost
```

Those are what make `did:web` resolution work from inside the network, and what let
oauth2-proxy perform OIDC discovery against the same browser-facing issuer URL a browser uses.

## Volumes

**`postgres_data` is the only named volume in the repository.** That is what makes
`docker compose down -v` against the **root** file destructive and the same flag against the
other two harmless. See [Running the stack](running-the-stack.md#destructive-operations).

Every other mount is a read-only bind of a file inside this repository:

| Mounted | Into |
|---|---|
| `services/caddy/Caddyfile` | caddy |
| `services/keycloak/realm-dataspaces-dev.json` | keycloak, for `--import-realm` |
| `services/keycloak/clients.effective.yaml` | `keycloak-sync` |
| `services/keycloak/organizations.yaml` | `keycloak-org-sync` |
| `services/oauth2-proxy/oauth2-proxy.cfg` | oauth2-proxy |
| `services/identity-registry/seed/` | the bootstrap one-shot |
| `services/connector/config/` | each EDC at `/config`, and the **provider** connector at `/edc-config` for the EDR signing key |
| `services/connector/governance/` | both connectors at `/governance` |

## The one-shot containers

Sixteen containers carry `restart: "no"`. They fall into three families.

**`*-db-create`** — a `postgres:17` container that waits for the database to accept
connections, then creates one database if it does not exist. Idempotent; every dependent waits
on `service_completed_successfully`, so a failure stops that branch cleanly.

**`*-db-init`** — the service's own image running `alembic upgrade head`. Idempotent. If it
fails, the service that owns the database does not start.

The EDC databases have no `*-db-init`: the EDC creates its own schema at boot.

**`identity-registry-bootstrap`** — a `sh -euc` script running about sixteen `ir-cli` commands
in order: bootstrap the trust anchor, register the provider and consumer participants, issue
data-subject credentials, bind them to the dev realm's user ids, import owners, agreements and
memberships.

Every command is idempotent, so it is safe on every start. It aborts at the first failure and
nothing depends on it, so a partial seed does not stop the stack — check its log if identity
behaves oddly after a fresh start.

**`keycloak-sync` and `keycloak-org-sync`** apply the realm contract — see
[keycloak](../services/keycloak.md).

## The real dataset-api file

`docker-compose.dataset-api.yml` builds three of its five services from directories **outside**
this repository. Every path is an environment variable with a default, so a checkout elsewhere
needs no edit:

| Variable | Points at |
|---|---|
| `DATASET_API_PATH` | the dataset-api checkout |
| `REC_REGISTRY_PATH` | the REC registry checkout |
| `CELINE_SDK_PATH` | the shared SDK checkout |

Both long-running services mount checked-out **source** over the installed package and set
`PYTHONPATH` so the mount wins — a development convenience, not a deployment shape.

Neither joins the `dataspaces` network; they reach ds services at `172.17.0.1:<port>` and
resolve the Keycloak hostname through an `extra_hosts` entry.

## Health checks

| Service | Probe |
|---|---|
| `postgres` | `pg_isready` |
| `keycloak` | a TCP open on the management port |
| `identity-registry`, both connectors, both provenance instances, the catalogue | `GET /health` |
| both EDCs | `GET /api/check/health` on the internal API port |
| `ds-portal` | `GET /` — there is no `/health` route |

`caddy`, `oauth2-proxy`, the dataset API mock and every one-shot declare none.

## Environment

Five services declare `env_file: [{path: .env.celine, required: false}]` — an optional hook for
a deployment that runs celine services beside ds. The file is absent by default and its absence
is a no-op; `.env.celine.example` is the template.

Everything else comes from the process environment, which the Taskfile populates from `.env`
and `.env.local` before invoking compose. See [Configuration](configuration.md).
