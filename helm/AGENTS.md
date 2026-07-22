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
| `ds-connector` | `CONNECTOR_OIDC_ISSUER_URL` set · `CONNECTOR_OIDC_INSECURE_DEV` false · `CONNECTOR_TRUST_ANCHOR_KEY_PATH` set · `CONNECTOR_VC_INSECURE_DEV` false · `EDC_API_KEY` not `insecure-dev-key` · `CONNECTOR_SERVICE_CLIENT_SECRET` not `svc-ds-connector` · `CONNECTOR_WEBHOOK_ALLOWED_HOSTS` set if webhooks enabled |
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

The KDF uses a per-key random salt stored alongside each ciphertext, so two
deployments with the same passphrase produce different encrypted blobs. A strong
per-deployment passphrase is still essential — the salt prevents precomputation
but does not compensate for a weak passphrase.

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

## Webhook SSRF protection

`POST /consent/request` accepts an optional `notification_url`. The connector
validates it against `CONNECTOR_WEBHOOK_ALLOWED_HOSTS` — a comma-separated
list of allowed hostnames. When the list is empty (the default), **all webhook
URLs are rejected**. The chart must set it explicitly if webhook notifications
are enabled (`CONNECTOR_NOTIFY_BACKENDS` includes `webhook`):

```yaml
- name: CONNECTOR_WEBHOOK_ALLOWED_HOSTS
  value: "notifications.example.com,hooks.internal.example.com"
```

## Supply-chain integrity

### Dockerfiles must use lockfiles

Fifteen `uv.lock` files are committed and current; **no Dockerfile uses any of
them**. `connector/Dockerfile:20-25` installs unpinned ranges with a
`2>/dev/null ||` fallback that silently installs a *different* dependency set on
resolution failure. Before building production images:

- Switch all Dockerfiles to `uv sync --frozen` (uses the committed lockfile,
  fails if it is stale rather than silently resolving different versions).
- Digest-pin base images (`python:3.12-slim@sha256:...`).

### CI security scanning

The only CI workflow (`compliance.yml`) runs governance-semantic checks. There
is no SAST, dependency scanning, container scanning, or secret scanning. Before
production:

- Enable Dependabot or `pip-audit` / `uv pip compile --audit` for dependency
  vulnerability scanning.
- Add a container-scan step (`trivy`, `grype`) to the image build pipeline.
- Add `task secrets:check` as a required CI gate on the release branch.

## Observability obligations

The platform currently has no log aggregation, no structured logging, and no
authorization-decision logging. For NIS2 Art. 21(2)(b) and the Art. 23 reporting
deadlines, a deployment needs retained, searchable evidence.

### What the chart must provide

- **Log shipping with defined retention.** Container logs are lost on restart
  without a cluster log shipper. The 24h/72h Art. 23 notification obligations
  cannot be evidenced without retained, searchable logs.
- **Prometheus scrape config** for the `/metrics` endpoints on `ds-connector`,
  `ds-provenance`, `ds-federated-catalog` and `dataset-api`. These endpoints
  are unauthenticated — expose them only to the in-cluster Prometheus, never
  through an Ingress.
- **Keycloak audit events** enabled and shipped (`eventsEnabled`,
  `adminEventsEnabled`, `adminEventsDetailsEnabled`).

### What the codebase needs before the chart can deliver

These are application-level prereqs, not chart concerns, but they block
meaningful observability:

1. **Structured JSON logging** with correlation/request IDs across services.
   There is exactly one `logging.basicConfig` in the whole repo
   (`federated_catalog/cli/main.py`). Without structured output, log shipping
   produces unsearchable text.
2. **Authorization-decision logging** — log every grant and deny with principal,
   permission, and resource. The natural home is
   `ds_auth.fastapi.require_permission`. Without this, auth failures leave no
   forensic trace.
3. **Metrics on all services.** `identity-registry` and `provenance` have no
   `metrics.py` — the two most security-relevant services are invisible to
   Prometheus.

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
- [ ] `CONNECTOR_WEBHOOK_ALLOWED_HOSTS` set if webhook notifications enabled
- [ ] TLS terminated for all browser- and DSP-facing endpoints
- [ ] Per-service database roles
- [ ] Pod `securityContext` hardening and resource limits
- [ ] Log shipping with a defined retention window
- [ ] `/metrics` endpoints reachable only from in-cluster Prometheus
- [ ] Dockerfiles use `uv sync --frozen`; base images digest-pinned
- [ ] CI includes dependency scanning and `task secrets:check`

## See also

- `.env.example` — the variable catalogue this chart implements
- `.agents/security-review.md` — findings and rationale behind these requirements
- Root `AGENTS.md` → "Security posture"
