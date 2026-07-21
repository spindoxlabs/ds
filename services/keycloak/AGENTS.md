# services/keycloak — Agent Guide

Config-only unit. No code, no Dockerfile, no Taskfile. Provides the OIDC realm,
the declarative service-client/scope definitions, and the native-organization
configuration for the whole platform.

Keycloak is the source of truth for **authentication** and for the **scope/group
vocabulary** that `libs/ds-auth` authorizes against. Getting a change wrong here
breaks authorization across every service at once.

## Layout

```
services/keycloak/
├── realm-dataspaces-dev.json        Dev realm import — users, groups, clients, org mapper
├── realm-production.example.json    Production realm reference (nothing selects it today)
├── clients.yaml                     Scopes + 7 service clients (celine-policies CLI)
└── organizations.yaml               KC native organizations + members (ir-cli org-sync)
```

## Runtime

Image `quay.io/keycloak/keycloak:26.6.0`, defined in the root `docker-compose.yml`.
Runs `start-dev --import-realm --http-port=9080`.

**Port 9080**, not 8080. Browser-facing URLs go through Caddy at
`http://keycloak.dataspaces.localhost:9010`. The healthcheck probes the
management port 9000, which is not published.

Key env: `KC_BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` (dev: `admin`/`admin`),
`KC_HTTP_ENABLED=true`, `KC_HOSTNAME=http://keycloak.dataspaces.localhost:9010`,
`KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`, `KC_PROXY_HEADERS=xforwarded`,
`KC_SPI_LOGIN_DEFAULT_REALM_NAME=dataspaces`.

## Provisioning chain — ordering matters

Three containers run in sequence; each depends on the previous being healthy or
completed:

1. **`keycloak`** — imports `realm-dataspaces-dev.json`, becomes healthy.
2. **`keycloak-sync`** — image `ghcr.io/celine-eu/celine-policies:dev`. Runs
   `celine-policies keycloak bootstrap` then `keycloak sync --secrets-file`,
   reading `clients.yaml`. Creates the scopes and the service clients.
3. **`keycloak-org-sync`** — built from the identity-registry Dockerfile. Runs
   `ir-cli keycloak org-sync --config /app/organizations.yaml`. Creates KC native
   organizations and assigns members.

`task keycloak:reload` tears down and restarts the chain.

> The realm import only seeds users, groups and the `ds-portal` client. Service
> clients come from `clients.yaml` via step 2 — editing the realm JSON to add a
> service client is the wrong layer.

## `clients.yaml` — the permission vocabulary

Realm `dataspaces`. 16 scopes in 5 families:

```
dataset.{admin,query,read,write}
identity-registry.{admin,read,resolve,membership.read}
connector.{admin,provider.read,provider.write,history.read,internal,webhook}
provenance.{read,write}
catalog.read
```

Seven service clients. **Each secret defaults to its own `client_id`** — a dev
convenience that must be overridden in production (see Security below).

| client_id | default_scopes | Override env |
|-----------|----------------|--------------|
| `svc-ds-identity-registry` | `identity-registry.admin` | `SVC_DS_IDENTITY_REGISTRY_SECRET` |
| `svc-ds-onboarding` | `identity-registry.admin` | `SVC_DS_ONBOARDING_SECRET` |
| `svc-ds-portal` | `dataset.query`, `dataset.read`, `identity-registry.resolve`, `identity-registry.read`, `connector.admin`, `connector.history.read`, `provenance.read`, `catalog.read` | `SVC_DS_PORTAL_SECRET` |
| `svc-ds-connector` | `identity-registry.read`, `identity-registry.membership.read`, `provenance.write` | `SVC_DS_CONNECTOR_SECRET` |
| `svc-ds-federated-catalog` | `identity-registry.read` | `SVC_DS_FEDERATED_CATALOG_SECRET` |
| `svc-ds-dataset-api` | `connector.internal` | `SVC_DS_DATASET_API_SECRET` |
| `svc-edc` | `identity-registry.read`, `connector.webhook` | `SVC_EDC_SECRET` |

`extra_audiences` lets a client's token be accepted by another service — that is
how `svc-ds-portal` calls four different backends with one token.

## How claims reach the services

`ds_auth.extract_groups` merges realm-level `groups` with
`organization.<alias>.groups`. `ds_auth.extract_organizations` parses
`organization.<alias>.{type,attributes}`.

- **Service tokens** authorize on the `scope` claim.
- **User tokens** authorize on merged **groups**. Group names mirror scope names.

> `ds_auth` reads `organization.<alias>.groups` — **not** `.roles`. Some older
> docs claim `.roles`; the config file and the library both use `groups`.

## `organizations.yaml`

Defines KC native organizations and their members, keyed by email, each with a
`groups:` list. Provisioned by `ir-cli keycloak org-sync` (`--strict` fails on
unresolvable members, suitable for CI).

**Two independent membership systems exist:**

| System | Authority for | Source |
|--------|---------------|--------|
| KC organizations | Portal UX gating only | `organizations.yaml` |
| IR `OrganizationMembership` | Data-access decisions | identity-registry DB |

They never query each other. The portal reads JWT claims for UX; every data
access decision goes through the identity-registry API.

## Dev credentials

Defined in `realm-dataspaces-dev.json`. See the root `AGENTS.md` dev-credentials
table. All four users have `password == username` and `"temporary": false`.

## Common tasks

| Task | Where |
|------|-------|
| Add a scope | `clients.yaml` → `scopes:` |
| Add a service client | `clients.yaml` → `clients:` |
| Grant a service a new permission | `clients.yaml` → that client's `default_scopes` |
| Let service A call service B | add B's client_id to A's `extra_audiences` |
| Add a user group | realm JSON `groups:` |
| Add an organization or member | `organizations.yaml` |
| Re-provision after edits | `task keycloak:reload` |

## Security — production requirements

The dev realm is **not safe to deploy**. `docker-compose.yml` mounts
`realm-dataspaces-dev.json` directly; a production chart must select
`realm-production.example.json` instead. See `helm/AGENTS.md`.

Concrete differences that matter:

| Property | Dev realm | Required in production |
|----------|-----------|------------------------|
| Users | 4 users, password == username | none seeded |
| `ds-portal` secret | literal in the JSON | from a Secret |
| `directAccessGrantsEnabled` | `true` (ROPC) | `false` |
| `sslRequired` | `external` | `all` |
| Audit events | disabled | `eventsEnabled`, `adminEventsEnabled`, `adminEventsDetailsEnabled` all true |
| Brute-force protection | absent | `bruteForceProtected` + `failureFactor` |
| Password policy | absent | set one |
| Server mode | `start-dev` | `start --optimized` |
| Service client secrets | `client_id` | generated, from Secrets |

`realm-production.example.json` already gets most of this right — it enables the
audit flags, uses a confidential client, disables ROPC, and lists exact HTTPS
redirect URIs. Its only failing is that nothing selects it.

> A `scripts/keycloak_preflight.py` validator used to check exactly these
> properties (rejecting wildcards, ROPC, literal secrets, non-HTTPS URIs, and
> requiring audit events). It was removed with `scripts/`. Recovering an
> equivalent CI gate is worthwhile — the checks are in git history.

Also note `post.logout.redirect.uris` in the dev realm uses `/*` suffixes — a
minor open-redirect surface the production example avoids.
