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
├── clients.yaml                     What **ds** needs from a realm (hand-written)
├── clients.energy.yaml              What the **domain backend** needs (hand-written overlay)
├── clients.effective.yaml           GENERATED — core + overlays; what keycloak-sync applies
├── clients.host.generated.yaml      GENERATED — the ds section a *host* realm must carry
└── organizations.yaml               KC native organizations + members (ir-cli org-sync)
```

Two hand-written declarations, two generated ones. Regenerate both after any edit
to either hand-written file — `libs/ds-auth/tests/test_vocabulary.py` and
`services/identity-registry/tests/test_keycloak_merge.py` fail on a stale copy:

```bash
task keycloak:merge     # → clients.effective.yaml   (core + overlays)
task keycloak:mirror    # → clients.host.generated.yaml (core only)
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
   reading **`clients.effective.yaml`** (not `clients.yaml` — see the overlay
   section below). Creates the scopes and the service clients.
3. **`keycloak-org-sync`** — built from the identity-registry Dockerfile. Runs
   `ir-cli keycloak org-sync --config /app/organizations.yaml`. Creates KC native
   organizations and assigns members.

`task keycloak:reload` tears down and restarts the chain.

> The realm import only seeds users, groups and the `ds-portal` client. Service
> clients come from `clients.yaml` via step 2 — editing the realm JSON to add a
> service client is the wrong layer.

## The core / overlay split — and why the sync never sees the core file

`clients.yaml` declares what **ds** needs from a realm. `clients.<domain>.yaml`
declares what the **domain backend deployed alongside it** needs. Which one applies
is a deployment question, not a dev convenience:

| | declares | posture A (ds owns the realm) | posture B (ds is a guest) |
|---|---|---|---|
| `clients.yaml` | what **ds** needs | applied | mirrored across |
| `clients.<domain>.yaml` | what the **backend** needs | applied | **omitted** — the host declares its own services |

Dev only looks like the sole consumer because dev *is* a posture-A deployment that
happens to have an energy-domain backend.

> ### The merge is mandatory, and the reason is a silent failure
>
> `celine-policies keycloak sync` takes **exactly one file** — `config_path` is
> `dir_okay=False`, the load is a single `yaml.safe_load`. There is no include, no
> merge, no repeatable `--config`.
>
> `--prune` is opt-in and guards only orphan *scopes* and *clients*, so a split file
> will not delete them. **But scope assignments and audience mappers are recomputed
> and removed unconditionally**, outside the prune branch, for every client present
> in the file it was handed.
>
> So syncing the core alone does not delete `rec-registry.lookup` — it **strips the
> grant from `svc-ds-dataset-api`**, with no flag involved. The data-plane symptom
> is a row filter that resolves nobody: fewer rows, no error, no log.
>
> A client absent from the synced file entirely *is* left alone (it is an orphan).
> That asymmetry is the whole point: moving `svc-rec-registry` out is safe, moving a
> grant off a client that stays is not.

`ir-cli keycloak merge --overlay energy` resolves this by emitting the effective
file before the sync runs. An overlay may **add** scopes, **add** clients, and
**widen** a core client's `default_scopes` / `extra_audiences`. It may **not**
redefine a core client's identity (`secret`, `scopes_prefix`, `name`) or set
`realm` / `oauth2_proxy_client` — an overlay is a backend asking for grants, not a
second copy of the authority file. A named overlay that does not exist is an error,
never a thinner realm.

The host mirror (`task keycloak:mirror`) reads the **core** file and so carries no
domain system by construction: in a host realm those are the host's own services,
declared on the host's terms, and a mirror asking for them would be ds claiming
authority over another project's vocabulary.

## `clients.yaml` — the permission vocabulary

**Read the file.** This section used to enumerate the scopes and clients, and the
enumeration was wrong within two releases — it claimed "16 scopes in 5 families"
against a file that had grown well past that, and it still credited `svc-ds-portal`
with `connector.admin` long after that grant was removed on purpose. A permission
table maintained by eye beside the file it describes is a second source of truth
that only ever disagrees.

What is stable enough to write down:

- **Each secret defaults to its own `client_id`** — a dev convenience, overridden
  in production via `SVC_<CLIENT>_SECRET` (the `${VAR:-default}` in each entry).
- **No service client holds a `*.admin`.** Admin is an *operator* grant, held by
  an interactive revocable human, and it is a superset satisfying every
  `{service}.*` — including the machine-identity permissions a process should
  never inherit. `libs/ds-auth/tests/test_vocabulary.py` and the host mirror both
  enforce this; the mirror drops `*.admin` on the way across.
- **`connector.internal` and `connector.webhook` are in no bundle**, ever. They
  are checked with `require_exact_permission` because holding one means "I *am*
  that component", which is not something an administrator inherits.
- **`extra_audiences` is not decoration.** `ds_auth` verifies `aud`, so a token
  minted without the callee listed is rejected before its scopes are read.

To see the current state, and to check it rather than trust it:

```bash
task keycloak:merge     # what the sync applies (core + overlays)
task keycloak:mirror    # what a host realm must carry (core only)
task auth:test          # reconciles clients.yaml against the bundle table, both ways
```

`test_vocabulary.py` is the real guard: a scope in neither a bundle nor
`SERVICE_ONLY_PERMISSIONS` fails the build, because it is a permission no human
could ever be granted — almost always an oversight rather than a decision.

## How claims reach the services

`ds_auth.extract_groups` merges realm-level `groups` with
`organization.<alias>.groups`. `ds_auth.extract_organizations` parses
`organization.<alias>.{type,attributes}`.

- **Service tokens** authorize on the `scope` claim.
- **User tokens** authorize on merged **groups**, each naming a **role bundle**
  that expands into capabilities — see below.

> `ds_auth` reads `organization.<alias>.groups` — **not** `.roles`. Some older
> docs claim `.roles`; the config file and the library both use `groups`.

### Role bundles — groups no longer mirror scope names

A group used to be named exactly like the scope it granted, so the ~30-name scope
vocabulary had to exist as ~30 Keycloak groups. That made ds's internal API
surface something an external realm owner had to reproduce, and it could only be
provisioned by realm import.

A group now names one of five **bundles**, expanded by
`ds_auth.bundles.expand_bundles` inside `Principal.authority`:

| Bundle | Seat |
|---|---|
| `ds-admin` | dataspace operator — `identity-registry.admin`, `connector.admin`, provenance, catalogue |
| `ds-onboarding-operator` | reviews organisation applications and agreements; **cannot promote** |
| `ds-participant-admin` | one participant's provider console (org-scopeable) |
| `ds-participant-viewer` | read-only over the same surface |
| `ds-member` | authenticated human, catalogue only — a subject's/consumer's real authority is their **VC**, not a group |

Three rules matter when reading `bundles.py`:

- **The table is code, not configuration.** A permission table that can be edited
  at deploy time is a privilege-escalation surface. Mapping a *foreign* IdP's
  group names onto these bundles is a separate, deployment-owned concern —
  **Layer B**, two env-var maps:
  - `<SVC>_OIDC_GROUP_ALIASES` — foreign group name → ds **bundle**. An alias may
    only name a bundle, never a capability; anything else is dropped and logged, so
    deployment config cannot become a permission table. Set it on **every** service
    or on none: a half-wired map means authority depends on which service answered.
  - `CONNECTOR_OWNER_ALIASES` — foreign **organisation** name → ds `Owner.id`.
    Without it, per-owner scoping cannot work in a realm ds did not name.

  The dev realm carries `legacy-provider-admin`, a deliberately foreign-looking
  group that is **not** a bundle and grants nothing on its own; `.env.local` maps it
  to `ds-participant-admin` so `ds-e2e --flow user-authority` proves the translation
  path against a real token instead of only in unit tests.
- **Realm group vs org group is a real distinction, not two ways to spell one
  thing.** A realm group is a **deployment-wide** grant; an `organization.<alias>.groups`
  entry is scoped to that organisation. `ds_auth.Principal.grants_in(alias, perm)`
  asks the per-organisation question and the connector's provider perimeter uses it,
  so an operator who administers one owner and only reads another cannot write to the
  second. `extract_groups` still flattens both — that is correct for "may this caller
  do X at all" and useless for "to whose data", which is why both exist.
- **No bundle contains `connector.internal` or `connector.webhook`**, and
  `connector.admin` inside `ds-admin` cannot reach them either —
  `has_exact_permission` ignores the superset. CI asserts both
  (`libs/ds-auth/tests/test_vocabulary.py`), and `ds-e2e --flow user-authority`
  asserts it against a live token.
- **An unknown group passes through as its own capability.** That is what keeps a
  realm still carrying the old scope-named groups working, so the migration is
  additive. The one exception is a machine-identity permission, which is dropped
  however the group is named.

The portal expands the same table from a **generated** file
(`src/lib/server/bundles.generated.ts`). Never edit it — run
`task auth:bundles:generate`; `test_bundles_export.py` fails on drift.

### The login client needs an explicit `sub` mapper

A Keycloak **access** token carries `sub` only if the client has a mapper for it —
normally via the stock `basic` client scope. This realm does not have `basic`: a
realm import that declares its own `clientScopes` replaces the stock set, and
`celine-policies keycloak sync` manages the client's default scopes afterwards.
Listing a scope that does not exist is **silently ignored**.

The result was a token that authenticated, authorised and identified **nobody**:
`Principal.subject` was empty, so every provenance attribution of a human act
recorded `""`. An ID token carries `sub` regardless, so a browser login hides this
completely — it only surfaces where the access token is the identity, which is
everywhere ds authorises.

`oauth2_proxy` therefore carries an explicit `oidc-sub-mapper`, which owes nothing
to the realm's scope set. `ds-e2e --flow user-authority` asserts every seat's token
carries a `sub`, and `acting_principal` logs an error rather than writing a blank
attribution.

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
| Add a scope | `clients.yaml` → `scopes:`, then `task keycloak:merge` + `keycloak:mirror` |
| Add a service client | `clients.yaml` → `clients:`, then regenerate both |
| Grant a service a new permission | `clients.yaml` → that client's `default_scopes`, then regenerate both |
| Add a **domain backend's** scope or client | `clients.<domain>.yaml`, then `task keycloak:merge` |
| Grant a ds client a **domain** permission | `clients.<domain>.yaml` → that client's `default_scopes` (widens the core entry) |
| Let service A call service B | add B's client_id to A's `extra_audiences`, then regenerate |
| Add a realm-wide seat | realm JSON `groups:` (a bundle name) — needs a KC db reset |
| Add a participant-scoped seat | `organizations.yaml` member `groups:` — live, no reset |
| Change what a seat may do | `libs/ds-auth/src/ds_auth/bundles.py`, then `task auth:bundles:generate` |
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

## Scopes vs groups — different provisioning paths

Both authorize the same permission strings, but they arrive differently, and the
difference bites:

| | Defined in | Applied by | On a running stack |
|---|---|---|---|
| **Client scopes** | `clients.yaml` + `clients.<domain>.yaml`, merged into `clients.effective.yaml` | `keycloak-sync` init container | re-applied every run |
| **Realm groups** | `realm-*.json` | Keycloak's realm import | **only at first startup** |
| **Org groups** | `organizations.yaml` | `ir-cli keycloak org-sync` | re-applied every run |

So adding a *realm* group has no effect until the Keycloak database is recreated —
`task docker:restart` in dev, `celine-policies` in production. A new scope, by
contrast, appears after any `keycloak-sync`.

If a user's token is missing a realm group you just added, this is almost always
why.

**Role bundles make this mostly stop mattering.** The vocabulary is now five
fixed names rather than one per endpoint, so it changes when the *seats* change
rather than when the API does — and `org-sync` provisions bundles as **org
groups** against a live realm (`ensure_org_group`), which is the path that needs
no import. A realm-wide seat (`ds-admin`) still comes from the import; a
participant-scoped one (`ds-participant-admin`) does not.
