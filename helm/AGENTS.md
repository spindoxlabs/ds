# Helm deployment model — Agent Guide

> **Status: design contract, no chart yet.** This document defines what the
> chart must guarantee before any template is written. It is deliberately
> scoped to the *security-oriented configuration* — the wrapping of secrets,
> the production switch, and the trust material. Topology, autoscaling,
> ingress shape and storage classes are out of scope and will be iterated
> separately.

## Why this exists

The dev stack is zero-config by design: every service ships working defaults so
`task start` needs no `.env`. That is a deliberate developer-experience choice
and it is not a bug.

It becomes a liability only at one boundary — a deployment that inherits those
defaults silently. The chart is that boundary. Its first responsibility is not
to deploy the platform; it is to **make an insecure deployment impossible to
produce by omission**.

## The core mechanism: `DS_ENV=production`

Every Python service constructs a `ProductionGuard`
(`libs/ds-auth/src/ds_auth/production.py`) during startup and registers the
values that are dangerous when left at their dev defaults.

| `DS_ENV` | Behaviour |
|----------|-----------|
| unset or `dev` | Each violation is logged as a warning; the service starts. This is the laptop path. |
| `production` | **All** violations are collected, logged together, and the service refuses to start. |

The guard reports every violation in one pass rather than failing on the first,
so a chart author gets the complete list from a single failed deploy instead of
discovering them one rollout at a time.

**The chart MUST set `DS_ENV=production` on every service container.** This is
the single switch that converts the entire warn-only posture into fail-closed.
It is not a per-service opt-in and must not be exposed as a toggle that a values
file can quietly turn off — treat it as a constant of the production chart.

```yaml
# every Deployment/StatefulSet pod spec
env:
  - name: DS_ENV
    value: production
```

### What the guard currently enforces

| Service | Registered checks |
|---------|-------------------|
| `ds-connector` | `CONNECTOR_OIDC_ISSUER_URL` set · `CONNECTOR_OIDC_INSECURE_DEV` false · `CONNECTOR_TRUST_ANCHOR_KEY_PATH` set · `CONNECTOR_VC_INSECURE_DEV` false · `EDC_API_KEY` not `insecure-dev-key` · `CONNECTOR_SERVICE_CLIENT_SECRET` not `svc-ds-connector` |
| `identity-registry` | `IDENTITY_REGISTRY_OIDC_ISSUER_URL` set · `IDENTITY_REGISTRY_OIDC_INSECURE_DEV` false · `IDENTITY_REGISTRY_ENCRYPTION_KEY` not the dev passphrase · `KEYCLOAK_CLIENT_SECRET` not `insecure-dev-secret` |
| `ds-provenance` | `PROVENANCE_OIDC_ISSUER_URL` set · `PROVENANCE_OIDC_INSECURE_DEV` false |
| `ds-federated-catalog` | `CATALOG_OIDC_ISSUER_URL` set · `CATALOG_OIDC_INSECURE_DEV` false · `CATALOG_SERVICE_CLIENT_SECRET` not `svc-ds-federated-catalog` |

The guard also rejects universally weak values (`admin`, `postgres`, `password`,
`changeme`, empty) for any registered setting, so a default nobody remembered to
register is still caught if it looks like one.

**When adding a new setting with a dev default, register it with the guard in
the same change.** A new insecure default that is not registered is invisible to
the chart.

## Surfaces the guard cannot reach

Three components are not Python and need their protection expressed in the chart
itself.

### 1. EDC (Java)

- **`DS_DEMO_IDENTITY_ENABLED` must never be set.** The `DemoIdentityFallbackExtension`
  accepts self-issued DCP tokens *without verifying their signature* whenever the
  real verifier rejects them — a complete DSP authentication bypass. The Java
  default is `false`; dev compose sets it to `true` explicitly. The chart simply
  omits it. Do not add it to `values.yaml` at all — an absent key cannot be
  accidentally set to `true`.
- **`EDC_API_KEY`** must come from a Secret, with no chart-level default. Prefer
  the file form (`EDC_API_KEY_FILE`) and mount the Secret as a file — the
  connector already supports it (`services/connector/src/connector/config.py`).
- **`edc.iam.did.web.use.https`** must be `true`. In dev it is `false` so
  `did:web` resolution works over plain HTTP against Caddy. In production, DID
  documents carry the public keys used for trust decisions; fetching them over
  HTTP means an on-path attacker controls participant identity verification.
- **`edc.sql.schema.autocreate`** should be `false`. Dev lets the EDC run DDL as
  the Postgres superuser at every boot; production should migrate as a separate,
  gated step with a restricted role.
- **Management APIs (`19193`/`29193`) and control APIs (`19192`/`29192`) must not
  be exposed.** ClusterIP only, never an Ingress. They create and delete assets,
  policies and transfers.

### 2. Portal (Node/SvelteKit)

- **`AUTH_SECRET`** keys Auth.js session encryption. `hooks.server.ts` currently
  falls back to a literal when it is unset; the chart must always supply it from
  a Secret. A known value means forgeable portal sessions carrying arbitrary
  user identity and VC claims.
- **`ORIGIN`** must match the public HTTPS URL and the Keycloak redirect URI.

### 3. Keycloak

- The dev realm (`services/keycloak/realm-dataspaces-dev.json`) contains four
  users whose password equals their username, a literal client secret,
  `directAccessGrantsEnabled: true`, and `sslRequired: external`. **It must never
  be imported by a production deployment.** `realm-production.example.json` is
  the correct reference; the chart selects it explicitly rather than defaulting.
- Run Keycloak with `start --optimized`, not `start-dev`.
- Every entry in `services/keycloak/clients.yaml` defaults its secret to its own
  `client_id`. Several of those clients hold admin-level scopes
  (`svc-ds-portal` → `connector.admin`; `svc-ds-onboarding` →
  `identity-registry.admin`). All must be overridden from Secrets.
- Enable `bruteForceProtected`, a `passwordPolicy`, and the audit event flags
  (`eventsEnabled`, `adminEventsEnabled`, `adminEventsDetailsEnabled`) — the last
  three are the only Keycloak-side audit trail available for NIS2 evidence.

> **Note:** a `scripts/keycloak_preflight.py` validator previously existed that
> checked exactly these realm properties. It was removed along with `scripts/`.
> Re-introducing an equivalent realm gate in CI is tracked as follow-up work; the
> checks it performed are worth recovering from git history.

## Secret and key material

`.env.example` is the authoritative catalogue of every variable, what it does,
and its blast radius if leaked. **The chart's `values.yaml` and Secret templates
should map 1:1 onto it** — if a variable is documented there and absent from the
chart, that is a gap.

### Bootstrapping

```bash
task secrets:bootstrap    # = secrets:generate + secrets:keygen
task secrets:check        # refuse to ship a file that still carries dev defaults
```

Both are idempotent: existing values and existing key files are preserved, so
re-running only fills what is missing. Nothing is ever overwritten.

- `task secrets:generate` renders `.env.production` from `.env.example`,
  replacing each `CHANGE_ME` secret with generated entropy and listing the
  values that still need human input (hostnames, DIDs, URLs).
- `task secrets:keygen` writes EC P-256 key material to `secrets/` — EDR signing
  keys for both EDC vaults and the trust-anchor keypair. Private JWKs feed the
  EDC vault and identity-registry; `*.public.jwk.json` is what
  `CONNECTOR_TRUST_ANCHOR_KEY_PATH` points at.
- `task secrets:check` fails on any remaining `CHANGE_ME`, any known dev default,
  any service secret still equal to its client id, `DS_DEMO_IDENTITY_ENABLED=true`,
  and a missing `DS_ENV=production`. **Wire this into the release pipeline.**

`secrets/` and `.env.*` are gitignored.

### The EDC vault files are dev fixtures

`services/connector/config/{provider,consumer}-vault.properties` carry EC P-256
private keys and `insecure-dev-secret`. These are **zero-config dev material**,
committed on purpose so the stack runs with no setup — the same category as
`.env.local`.

A production deployment must not mount them. Render the vault from Secrets built
by `task secrets:keygen` instead, and treat the committed values as public.
`FilesystemVaultSeederExtension` loads whatever it is given without placeholder
detection, so this is a chart responsibility, not a runtime one.

### Encryption key durability

`IDENTITY_REGISTRY_ENCRYPTION_KEY` Fernet-encrypts every participant DID private
key at rest. **Losing it makes every stored private key unrecoverable.** It
belongs in a backed-up secret store, not only in a cluster Secret. Rotating it
requires re-encrypting the key table — there is no automatic migration path today.

Related known weakness: the KDF uses a hardcoded global salt
(`services/identity-registry/src/identity_registry/services/crypto.py`), so the
derived key is deterministic per passphrase across all deployments. A strong
per-deployment passphrase mitigates this; fixing the salt is tracked separately.

## Networking and least privilege

Two structural items the chart should get right from the start, because they are
expensive to retrofit:

- **Use in-cluster DNS for service-to-service traffic.** Compose routes
  container-to-container calls through the host gateway (`172.17.0.1`) and
  published ports. That convention is a dev artifact; carrying it into
  Kubernetes would force privileged ports to stay exposed. Every URL in
  `.env.example`'s "internal service URLs" section is already written in
  service-name form for this reason.
- **One database role per service.** Dev uses a single Postgres superuser for all
  six databases. The chart should provision distinct least-privilege roles;
  `.env.example` has a separate URL per service precisely so this is possible
  without code changes.

Also expected of any production pod spec, none of which the dev compose sets:
`securityContext` with `runAsNonRoot` (the images already create non-root users
and set `USER`), `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`,
`readOnlyRootFilesystem` where feasible, and resource requests/limits.

## Observability obligations

The platform currently has no log aggregation, no structured logging, and no
authorization-decision logging. For NIS2 Art. 21(2)(b) and the Art. 23 reporting
deadlines, a deployment needs retained, searchable evidence. The chart is the
natural place to require:

- a logging sidecar or cluster log shipper with a defined retention window;
- scrape configuration for the `/metrics` endpoints that exist on `ds-connector`,
  `ds-provenance`, `ds-federated-catalog` and `dataset-api`
  (note: these are currently **unauthenticated** — either gate them or keep them
  off any public Ingress);
- Keycloak audit events enabled and shipped.

## Checklist before a chart is considered production-ready

- [ ] `DS_ENV=production` on every service container
- [ ] Every `CHANGE_ME` in `.env.example` mapped to a Secret or values entry
- [ ] `task secrets:check` passes in the release pipeline
- [ ] `DS_DEMO_IDENTITY_ENABLED` absent from the chart entirely
- [ ] `realm-production.example.json` selected; dev realm unreachable
- [ ] EDC management/control ports ClusterIP-only, no Ingress
- [ ] `edc.iam.did.web.use.https=true`, `edc.sql.schema.autocreate=false`
- [ ] EDC vault rendered from generated keys, not the committed dev files
- [ ] `IDENTITY_REGISTRY_ENCRYPTION_KEY` in a backed-up secret store
- [ ] TLS terminated for all browser- and DSP-facing endpoints
- [ ] Per-service database roles
- [ ] Pod `securityContext` hardening and resource limits
- [ ] Log shipping with a defined retention window

## See also

- `.env.example` — the variable catalogue this chart implements
- `.agents/security-review.md` — findings and rationale behind these requirements
- Root `AGENTS.md` → "Security posture"
