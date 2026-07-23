# Configuration reference

`helm/values.yaml` is the **one file an operator edits**. Helmfile loads it as
environment values and derives every per-release values document from it, so
there is no per-service file to keep in sync.

Secrets are not in this file — see [Secrets](secrets.md).

Anything absent from `values.yaml` has a safe default inside the chart. The
tables below list what is required or meaningful; per-chart defaults live in
`helm/charts/<chart>/values.yaml`.

## `global` — shared by every release

### Public addressing

Every public endpoint is a subdomain of `baseDomain`. Nothing else is exposed.

| Key | Default | Notes |
|-----|---------|-------|
| `global.baseDomain` | `ds.example.org` | **Change this.** Participant DIDs derive from it: `did:web:<participant>.<baseDomain>` |
| `global.hosts.portal` | `portal` | → `portal.<baseDomain>`, the only human-facing host |
| `global.hosts.trustAnchor` | `trust-anchor` | → trust-anchor DID document + StatusList2021 |
| `global.hosts.users` | `users` | user DID resolution; only used when `authority.identityRegistry.exposeUserDids` is true |

Changing `baseDomain` after participants have been onboarded changes their DIDs.
Treat it as immutable once a dataspace is live.

### Namespaces

| Key | Default | Notes |
|-----|---------|-------|
| `global.namespaces.authority` | `ds-authority` | one trust boundary |
| `global.namespaces.participantPrefix` | `ds-` | each participant lands in `<prefix><name>` |

### Images

| Key | Default | Notes |
|-----|---------|-------|
| `global.image.registry` | `ghcr.io/spindoxlabs` | |
| `global.image.prefix` | `ds-` | composed as `<registry>/<prefix><service>` |
| `global.image.tag` | `""` | empty → each chart's `appVersion` |
| `global.image.pullPolicy` | `IfNotPresent` | |
| `global.image.pullSecrets` | `[]` | e.g. `[{name: ghcr-credentials}]` |

A per-chart `image.digest` wins over any tag. Digest-pinning is the recommended
production form.

### Ingress and TLS

| Key | Default | Notes |
|-----|---------|-------|
| `global.ingress.className` | `nginx` | |
| `global.ingress.controllerNamespace` | `ingress-nginx` | the NetworkPolicies allow ingress **only** from this namespace |
| `global.ingress.annotations` | `{}` | merged into every Ingress |
| `global.ingress.tls.clusterIssuer` | `letsencrypt-prod` | cert-manager issues per host |
| `global.ingress.tls.secretName` | `""` | set → used verbatim, `clusterIssuer` ignored (pre-created / wildcard cert) |

`ssl-redirect` and `force-ssl-redirect` are always on. The TLS secret name is
derived from the **host**, not from the Ingress object, because a host served by
several Ingress objects must share one certificate — see
[Exposure](exposure.md#one-certificate-per-host).

### PostgreSQL

Provisioned externally with CloudNativePG ([Prerequisites](prerequisites.md)).
The charts only address it.

| Key | Default | Notes |
|-----|---------|-------|
| `global.postgres.host` | `ds-pg-rw.database.svc.cluster.local` | |
| `global.postgres.port` | `5432` | also the port opened by the default-deny egress rule |
| `global.postgres.sslMode` | `require` | |
| `global.postgres.databases.identityRegistry` | `identity_registry` | |
| `global.postgres.databases.connectorPrefix` | `connector` | → `connector_<participant>` |
| `global.postgres.databases.provenancePrefix` | `provenance` | → `provenance_<participant>` |
| `global.postgres.databases.edcPrefix` | `edc` | → `edc_<participant>` |

One database **and one least-privilege owner role** per service. The password
never lands in a ConfigMap or a rendered URL: `DB_USER`/`DB_PASSWORD` come from
the Secret and Kubernetes interpolates them into the connection string with
`$(VAR)`.

### Keycloak

Externally managed; see [Keycloak requirements](keycloak.md).

| Key | Default | Notes |
|-----|---------|-------|
| `global.keycloak.realm` | `dataspaces` | |
| `global.keycloak.issuerUrl` | — | **Required.** With `DS_ENV=production` every service refuses to start without it; it is what makes `ds_auth` verify JWT signature, audience and issuer via JWKS |
| `global.keycloak.adminUrl` | — | only used by the optional sync init containers |
| `global.keycloak.tokenUrl` | — | client-credentials endpoint for service tokens |
| `global.keycloak.sync.enabled` | `false` | opt-in provisioning of clients/organizations into the external realm |
| `global.keycloak.sync.clientsConfigMap` | `""` | ConfigMap holding `clients.yaml` |
| `global.keycloak.sync.organizationsConfigMap` | `""` | ConfigMap holding `organizations.yaml` |

Leaving `sync.enabled` false keeps Keycloak admin credentials out of the
application namespace entirely. Prefer provisioning the realm out-of-band.

### Posture

| Key | Default | Notes |
|-----|---------|-------|
| `global.networkPolicy.enabled` | `true` | default-deny ingress **and** egress, explicit allows only |
| `global.monitoring.serviceMonitor` | `false` | also gates the `/metrics` NetworkPolicy |
| `global.monitoring.prometheusNamespace` | `monitoring` | the only namespace allowed to reach `/metrics` |
| `global.externalSecrets.enabled` | `false` | true → emit `ExternalSecret` CRs instead of `Secret`s |
| `global.externalSecrets.secretStoreRef` | `{}` | e.g. `{name: vault-backend, kind: ClusterSecretStore}` |
| `global.resources` | 100m/256Mi req, 512Mi limit | applied to every service unless overridden per-chart |

`/metrics` is unauthenticated on `ds-connector`, `ds-provenance` and
`ds-federated-catalog`. It is never routed through an Ingress, and the
NetworkPolicy that permits scraping is only rendered when `serviceMonitor` is
enabled.

## `authority` — deploy once per dataspace

| Key | Default | Notes |
|-----|---------|-------|
| `authority.enabled` | `true` | helmfile `condition` on the whole release |
| `authority.identityRegistry.replicaCount` | `1` | migrations run as an init container; see below |
| `authority.identityRegistry.trustAnchorDomain` | `trust-anchor.ds.example.org` | must match `global.hosts.trustAnchor` + `baseDomain` |
| `authority.identityRegistry.exposeUserDids` | `false` | publish `users.<baseDomain>`; needed only when **remote** verifiers resolve your user DIDs |
| `authority.identityRegistry.credentialService.expose` | `false` | publish the DCP presentation-query endpoint; in the EDC DCP flow the holder self-presents, so remote verifiers normally never call it |
| `authority.identityRegistry.bootstrap.enabled` | `true` | `ir-cli bootstrap` + seed import as an init container |
| `authority.identityRegistry.bootstrap.seedConfigMap` | `""` | ConfigMap with `owners.yaml` and/or `bootstrap.sh`; empty → the image's baked-in defaults |
| `authority.identityRegistry.bootstrap.seedMountPath` | `/seed` | |

Bootstrap is idempotent by design — every `ir-cli` command has upsert semantics —
so it is safe on every pod start.

## `participants` — one release group each

A list. Each entry produces up to five releases named `ds-<service>-<name>`, in
namespace `<participantPrefix><name>`.

| Key | Default | Notes |
|-----|---------|-------|
| `name` | — | **Required.** Also the participant's public host and DID: `did:web:<name>.<baseDomain>` |
| `enabled` | — | false → the whole group is skipped |
| `role` | — | `provider` or `consumer`; surfaces as a pod label and in service config |
| `did` | `""` | empty → derived. Override only to pin an existing DID |
| `datasetApi.url` | `""` | the dataset API is **participant-operated and external**; the charts only pass its URL |

### Per-service keys

| Key | Default | Notes |
|-----|---------|-------|
| `connector.replicaCount` | `1` | |
| `connector.notifyBackends` | `"null"` | `null` \| `smtp` \| `webhook`, comma-separated |
| `connector.webhookAllowedHosts` | `[]` | SSRF guard. **An empty list rejects every webhook URL** — required if `notifyBackends` includes `webhook` |
| `connector.governanceOverlayName` | `""` | merges `governance.<name>.yaml` on top of the base file |
| `connector.governanceConfigMap` | `""` | empty → the image's baked-in `governance.yaml` |
| `provenance.replicaCount` | `1` | |
| `edc.replicaCount` | `1` | |
| `federatedCatalog.enabled` | `false` | catalog crawling is a **consumer-side** operation |
| `federatedCatalog.replicaCount` | `1` | |
| `federatedCatalog.crawlInterval` | `300` | seconds |
| `portal.enabled` | `false` | the portal is deployed alongside exactly one participant |
| `portal.replicaCount` | `1` | |

## Chart-level keys worth knowing

These are not in `helm/values.yaml` but are settable per release if you need to
deviate. They live in `helm/charts/<chart>/values.yaml`.

| Key | Chart | Default | Notes |
|-----|-------|---------|-------|
| `existingSecret` | all | `""` | reference a pre-created Secret; the chart then creates none |
| `migration.enabled` | Python services | `true` | Alembic `upgrade head` as an init container |
| `migration.mode` | Python services | `initContainer` | `job` mode is reserved for a later iteration |
| `sqlSchemaAutocreate` | `ds-edc` | `true` | see the deviation note below |
| `didWebUseHttps` | `ds-edc` | `true` | **do not change.** Kept as a value only to make the invariant visible |
| `ports.*` | `ds-edc` | 19191/19192/19193/19194/19291 | uniform across participants — each EDC is namespace-isolated |
| `connectorServiceName` | `ds-edc`, `ds-federated-catalog` | `""` | empty → this participant's own connector |
| `credentialTtl.defaultDays` / `maxDays` | `ds-identity-registry` | 365 / 730 | issued-credential lifetime |
| `maxLineageDepth` | `ds-provenance` | `20` | |
| `auth.keycloakClientId` | `ds-portal` | `ds-portal` | the **public** OIDC redirect client, not a service client |

!!! note "Two deliberate deviations from the security contract"
    **`edc.sql.schema.autocreate` defaults to `true`, not `false`.** The contract
    prefers `false` to avoid superuser DDL at every boot. The charts instead give
    each EDC a least-privilege role that owns only its own database, which
    removes the actual risk while keeping the connector self-migrating. Set
    `sqlSchemaAutocreate: false` and run Flyway out-of-band for the strictest
    posture.

    **The connector has no public Ingress, but the dataset API is external.**
    In-cluster, `/internal/*` is reachable only from the same namespace. If your
    dataset API runs outside the cluster, arrange connectivity yourself — run it
    in-namespace, or add a dedicated internal Ingress carrying the `X-Api-Key`.
    The charts do not expose `/internal` publicly by default.

## Replicas and migrations

Migrations run as an **init container**, which means one run per pod. With
`replicaCount > 1` concurrent runs serialise on Postgres locks rather than
conflicting — Alembic's transactional DDL makes this safe but not free. The
charts default migration-carrying services to a single replica, and expose
`migration.mode` so a future iteration can switch to a pre-upgrade Job without a
template rewrite.

A `PodDisruptionBudget` with `minAvailable: 1` is rendered automatically whenever
`replicaCount > 1`.
