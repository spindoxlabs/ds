# Helm deployment model — Agent Guide

> **Status: all seven charts implemented and rendering end-to-end.** `ds-common`
> (library), `ds-namespaces`, the authority `ds-identity-registry`, and the
> participant tier `ds-edc` / `ds-connector` / `ds-provenance` /
> `ds-federated-catalog` / `ds-portal`. `helmfile.yaml.gotmpl` composes an
> authority plus any number of participants through SOPS. Remaining work is
> hardening and CI gates — see the checklist at the end of this file.
>
> The security contract below is the invariant set; the sections after it
> describe *what exists on disk* and how to work in this folder. See
> `.agents/helm/plan.md` for the design and phasing.

> **Operator documentation lives in `docs/deployment/`**, published as the
> Deployment section of the mkdocs site: prerequisites, the Keycloak realm
> contract, the key-by-key `values.yaml` reference, the secret key reference,
> exposure/NetworkPolicy, and day-2 operations. Keep it in sync when you change
> a chart's values contract or its public surface — it is the only operator-
> facing description of either. This file stays agent- and security-facing.

## Working in this folder

### Layout

```
helm/
├── AGENTS.md                    # this file — security contract + ops notes
├── README.md                    # short runbook; points at docs/deployment/
├── helmfile.yaml.gotmpl         # release composition; MUST keep .gotmpl extension
├── values.yaml                  # the ONE operator-edited file
├── secrets.example.yaml         # template → copy to secrets.sops.yaml
├── secrets.sops.yaml            # SOPS-encrypted, committed; plaintext NEVER committed
├── .sops.yaml                   # SOPS creation rules (set your age/KMS recipient)
├── docs/
│   └── cnpg-cluster.example.yaml   # reference CNPG Cluster (databases + roles)
└── charts/
    ├── ds-common/               # library chart — ALL shared helpers live here
    ├── ds-namespaces/           # labeled namespaces (participant label → NetPols)
    ├── ds-identity-registry/    # authority release
    ├── ds-edc/                  # participant: Eclipse EDC (only public DSP surface)
    ├── ds-connector/            # participant: orchestration/consent (internal)
    ├── ds-provenance/           # participant: PROV-O lineage (internal)
    ├── ds-federated-catalog/    # participant: DCAT-AP crawler (internal, optional)
    └── ds-portal/               # participant: SvelteKit UI (only human host, optional)
```

The federated catalog crawls the dataspace through a **consumer-capable**
connector (in dev it targets the consumer connector on 31001). `connectorServiceName`
defaults to the same-participant connector; set it explicitly if the catalog
runs under a participant whose connector cannot perform DSP catalog requests.

### Conventions that will bite you if ignored

- **`helmfile.yaml.gotmpl`, not `helmfile.yaml`.** Helmfile v1 only templates
  `{{ .Values.* }}` in the release list when the file carries the `.gotmpl`
  extension. Plain `.yaml` fails with a cryptic map-key error.
- **All boilerplate lives in `ds-common/templates/*.tpl`.** Naming, labels,
  image composition, security contexts, the `DS_ENV` injection, secret-mode
  switching, DB URL assembly, ingress TLS, probes, NetworkPolicy builders.
  A service chart that hand-rolls any of these is doing it wrong — add or extend
  a helper instead. Helpers are namespaced `ds.*`.
- **Go-template comments cannot contain `*/`.** A literal `*/` (e.g. a glob like
  `services/*/Dockerfile`) inside `{{/* ... */}}` closes the comment early and
  breaks the parse. Reword.
- **`ds-common` is a `file://` dependency.** After editing it, run
  `helm dependency update ./charts/<service>` (or delete `charts/<service>/charts/`)
  before re-rendering, or you test a stale vendored copy.
- **One cert-manager Certificate per host.** Several Ingress objects can share a
  host (each rewrite behaviour needs its own object, since `rewrite-target` is a
  per-object annotation). Only ONE of them may carry the `cluster-issuer`
  annotation — pass `issueCert true` to `ds.ingress.annotations` on exactly one,
  `false` on the rest. `ds.ingress.tls` derives the secret name from the host so
  they share the cert.
- **Numeric UID is mandatory.** `runAsNonRoot` cannot be verified against an
  image whose `USER` is a name; kubelet refuses to start the pod. All service
  Dockerfiles pin uid/gid **10001** (`podSecurityContext.runAsUser`). If you add
  a service, pin its uid the same way.

### Validate before committing

```bash
helm dependency update ./charts/ds-identity-registry
helm lint ./charts/ds-identity-registry \
  --set secrets.identityRegistryEncryptionKey=x \
  --set secrets.keycloakClientSecret=y --set secrets.dbPassword=z

# full helmfile render through SOPS (needs SOPS_AGE_KEY_FILE)
helmfile -e production template
```

Secret templates use `required`, so a render that succeeds proves every
mandatory secret is wired. A render that fails names the missing key.

### Adding a service chart

1. `charts/ds-<svc>/` with `Chart.yaml` depending on `ds-common` (`file://../ds-common`).
2. A `templates/_env.tpl` mapping the service's `pydantic-settings` env prefix
   (grep `env_prefix=` in `services/<svc>/src/*/config.py`) onto values.
3. Standard object set: deployment, service, serviceaccount, secret,
   externalsecret, networkpolicy, pdb, and ingress *only if* §Exposure lists it.
4. A `global:` fallback block in the chart's `values.yaml` so it renders
   standalone under `helm lint`; real values arrive from `helm/values.yaml` via
   helmfile.
5. A release entry in `helmfile.yaml.gotmpl`, participant-scoped with
   `needs: [<authority ns>/ds-identity-registry]`.
6. Update the checklist in this file and the plan's phasing table.

### Cross-release addressing (participant charts)

A participant's charts are separate releases but must address each other's
Services. Do **not** derive a sibling's name from `.Release.Name` — derive it
from the participant name:

- Releases are named `ds-<service>-<participant>` (helmfile enforces this).
- Each release name contains its chart name, so the Service fullname collapses
  to the release name.
- Therefore `ds-edc-<participant>`, `ds-provenance-<participant>`,
  `ds-connector-<participant>` are addressable from `.Values.participant.name`
  alone. The helpers `conn.edcService` / `conn.provenanceService` /
  `edc.connectorService` do exactly this.

The identity-registry lives in the authority namespace; participant charts reach
it at `ds-identity-registry.<authority-ns>.svc.cluster.local:30005`.

### Two deviations from the security contract, made deliberately

- **`edc.sql.schema.autocreate` defaults to `true`, not `false`.** The contract
  (below) prefers `false` to avoid superuser DDL at every boot. The charts give
  each EDC a *least-privilege role that owns only its own database*
  (`docs/cnpg-cluster.example.yaml`), which removes the actual risk — DDL as a
  cluster superuser — while keeping the connector self-migrating. It stays a
  value (`sqlSchemaAutocreate`); set it `false` and run Flyway out-of-band for
  the strictest posture.
- **The connector has no public Ingress, but the dataset API is external.** In
  compose the participant-operated dataset API calls the connector `/internal/*`
  over the Docker network. In-cluster that path is reachable only from the same
  namespace (NetworkPolicy). If the dataset API runs outside the cluster, the
  operator must arrange connectivity (run it in-namespace, or add a dedicated
  internal Ingress carrying the `X-Api-Key`) — the charts intentionally do not
  expose `/internal` publicly by default.

### did:web over HTTPS — where the `:80` Caddy hack went

The dev stack resolves `did:web` over plaintext `:80` through a Caddy rewrite.
The charts do not carry that: the participant host and the trust-anchor host
serve `/.well-known/did.json` over TLS on 443, and `edc.iam.did.web.use.https`
is `true`. The rewrite (`/.well-known/did.json` →
`/dids/did:web:<host>/did.json`) is a static per-host nginx `rewrite-target`
annotation. The participant host reaches the authority-namespace registry
through an `ExternalName` Service (`<edc>-identity-registry`), because an Ingress
can only target a Service in its own namespace.

---

> The remainder of this document is the **security contract** — the invariants
> every chart must hold regardless of topology. It is deliberately scoped to the
> security-oriented configuration: the wrapping of secrets, the production
> switch, and the trust material.

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

## Exposure

The design rule: **one public host per trust boundary, path-allowlisted, default
404.** A chart gets an `Ingress` only if it appears below. Everything else is
ClusterIP + NetworkPolicy and is reachable only from named in-cluster callers.

Operator-facing detail (paths, rewrites, per-service NetworkPolicy allows,
verification commands) is in `docs/deployment/exposure.md`. This section is the
invariant list.

### The three host shapes

| Host | Chart that owns the Ingress | Serves |
|------|-----------------------------|--------|
| `portal.<baseDomain>` | `ds-portal` | `/` — the only human-facing host. SSR, so the dev Caddy `/api/*` fan-in is **not** reproduced. |
| `<participant>.<baseDomain>` | `ds-edc` | `/.well-known/did.json` (rewritten to the authority registry via an `ExternalName`), `/protocol/*` → `:19194`, `/public/*` → `:19291`. Nothing else. |
| `trust-anchor.<baseDomain>` | `ds-identity-registry` | `/.well-known/did.json` (rewritten), `/status/*` (StatusList2021 — must be publicly fetchable, or revocation cannot be checked) |
| `users.<baseDomain>` | `ds-identity-registry` | `/<id>/did.json`, **only** when `exposeUserDids` — needed just for remote resolution of user DIDs |

The participant host **is** the participant's did:web identity, which is why DID
resolution and the DSP endpoints share it. One host, one Ingress owner: the
did:web path for a participant lives in `ds-edc`, not in the registry chart, and
crosses namespaces through an `ExternalName` Service because an Ingress can only
target a Service in its own namespace.

### Never exposed

EDC management (`:19193`) and control (`:19192`) — they create and delete assets,
policies and transfers. The connector (`:30001`, including `/internal/*` and
`/webhooks/*`), provenance (`:30000`), federated catalog (`:30003`). The
registry's `/admin/*`, `/sts/*`, `/credentials/*`, `/memberships/*`, `/owners/*`.
Every `/metrics` endpoint — all unauthenticated, restricted to the Prometheus
namespace by NetworkPolicy and never routed through an Ingress.

The `ds-edc` Service publishes management and control in-cluster, but
`fromIngressController` lists only `protocol` and `public`. The exposure is
denied twice — at routing and at the network layer — so a misconfigured Ingress
path still cannot reach them. **Keep both denials when editing that chart.**

`credentialService.expose` (DCP presentation query) defaults to `false`: in the
EDC DCP flow the holder self-presents, so remote verifiers do not call it. It is
authenticated when enabled, but it is attack surface with no default consumer.

### Two structural rules

- **One cert-manager Certificate per host.** Several Ingress objects share a host
  because `rewrite-target` is a per-object annotation. Exactly one may carry the
  `cluster-issuer` annotation — pass `issueCert true` to `ds.ingress.annotations`
  on that one and `false` on the rest. `ds.ingress.tls` derives the secret name
  from the host so they share the certificate.
- **Egress allows are opt-in per chart.** `ds.networkPolicy.defaultDeny` permits
  only DNS and Postgres; anything else must be listed. Broad-CIDR rules always
  exclude `169.254.169.254/32` — a pod that reaches the metadata endpoint can
  often mint cloud IAM credentials.

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

Legend: `[x]` implemented in the charts · `[~]` implemented for the authority
release, pending for participant charts · `[ ]` not yet.

- [x] `DS_ENV=production` on every service container — hardcoded in `ds.env.common`, not a value
- [x] Every `CHANGE_ME` in `.env.example` mapped to a Secret or values entry — all seven charts (identity-registry, edc, connector, provenance, portal, federated-catalog + namespaces)
- [ ] `task secrets:check` passes in the release pipeline
- [x] `DS_DEMO_IDENTITY_ENABLED` absent from the chart entirely
- [ ] `realm-production.example.json` selected; dev realm unreachable — external KC, see `docs/deployment/keycloak.md`
- [x] EDC management/control ports ClusterIP-only, no Ingress — `ds-edc` Service exposes them in-cluster; Ingress and `fromIngressController` NetPol list only protocol+public
- [x] `edc.iam.did.web.use.https=true` · `edc.sql.schema.autocreate` — `true` by design (per-DB owner role; see §deviations)
- [x] EDC vault rendered from generated keys, not the committed dev files — `ds-edc` Secret; committed fixtures never mounted
- [~] `IDENTITY_REGISTRY_ENCRYPTION_KEY` in a backed-up secret store — chart Secret + prominent backup warnings; the backup itself is operator-side
- [x] `CONNECTOR_WEBHOOK_ALLOWED_HOSTS` set if webhook notifications enabled — `ds-connector` value, empty rejects all
- [x] TLS terminated for all browser- and DSP-facing endpoints — cert-manager wired for authority, participant and portal ingress
- [x] Per-service database roles — `docs/cnpg-cluster.example.yaml`; charts consume one role per service, one DB per participant
- [x] Pod `securityContext` hardening and resource limits — enforced by `ds-common` for every chart; namespaces enforce PSA `restricted`
- [ ] Log shipping with a defined retention window
- [~] `/metrics` endpoints reachable only from in-cluster Prometheus — `ds.networkPolicy.metricsFromPrometheus` wired on `ds-connector`
- [ ] Dockerfiles use `uv sync --frozen`; base images digest-pinned — still unpinned (see §Supply-chain)
- [ ] CI includes dependency scanning and `task secrets:check`
- [x] Every JWT-verifying service has egress to the Keycloak JWKS endpoint (443) — `ds.networkPolicy.defaultDeny` opens only DNS and Postgres, so each chart adds the rule itself. `ds-identity-registry` and `ds-provenance` were missing it and would have failed every authenticated request under the default `networkPolicy.enabled: true`.

### Change made to the service Dockerfiles

Pinning `runAsNonRoot` required a numeric image UID. `services/*/Dockerfile`
were updated to create their `app`/`edc` user with an explicit **uid/gid
10001** (`useradd -u 10001` / `adduser -u 10001`). This is the only
application-repo change the charts depend on; keep it if you rework a Dockerfile.

## See also

- `docs/deployment/` — the operator documentation (published as the Deployment
  section of the docs site): prerequisites, Keycloak contract, `values.yaml`
  reference, secret reference, exposure, day-2 operations
- `.env.example` — the variable catalogue this chart implements
- `.agents/helm/plan.md` — design and phasing
- `.agents/security-review.md` — findings and rationale behind these requirements
- Root `AGENTS.md` → "Security posture"
