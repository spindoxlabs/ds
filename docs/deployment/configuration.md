# Configuration reference

`helm/values.yaml` is the **one file an operator edits**. Helmfile loads it as environment
values and derives every per-release values document from it, so there is no per-service file to
keep in sync.

Secrets are not in this file — see [Secrets](secrets.md).

Anything absent from `values.yaml` has a default inside the chart. The tables below list what is
required or meaningful; per-chart defaults live in `helm/charts/<chart>/values.yaml`.

## `global` — shared by every release

### Public addressing

| Key | Default | Notes |
|---|---|---|
| `global.baseDomain` | `ds.example.org` | **Change this.** Participant DIDs derive from it: `did:web:<participant>.<baseDomain>` |
| `global.hosts.portal` | `portal` | → `portal.<baseDomain>`, the only human-facing host |
| `global.hosts.trustAnchor` | `trust-anchor` | → the trust-anchor DID document and the revocation list |
| `global.hosts.users` | `users` | user DID resolution; used only when `exposeUserDids` is on |

Changing `baseDomain` after participants are onboarded **changes their DIDs**. Treat it as
immutable once a dataspace is live.

### Namespaces

| Key | Default | Notes |
|---|---|---|
| `global.namespaces.authority` | `ds-authority` | one trust boundary |
| `global.namespaces.participantPrefix` | `ds-` | each participant lands in `<prefix><name>` |

### Images

| Key | Default | Notes |
|---|---|---|
| `global.image.registry` | `ghcr.io/spindoxlabs` | |
| `global.image.prefix` | `ds-` | composed as `<registry>/<prefix><service>` |
| `global.image.tag` | `""` | empty → each chart's `appVersion` |
| `global.image.pullPolicy` | `IfNotPresent` | |
| `global.image.pullSecrets` | `[]` | e.g. `[{name: ghcr-credentials}]` |

A per-chart `image.digest` wins over any tag. **Digest-pinning is the recommended production
form.**

### Ingress and TLS

| Key | Default | Notes |
|---|---|---|
| `global.ingress.className` | `nginx` | |
| `global.ingress.annotations` | `{}` | merged into every Ingress |
| `global.ingress.tls.clusterIssuer` | `letsencrypt-prod` | cert-manager issues per host |
| `global.ingress.tls.secretName` | `""` | set → used verbatim, and `clusterIssuer` is ignored |
| `global.ingress.controllerNamespace` | `ingress-nginx` | the NetworkPolicies admit ingress **only** from this namespace |

`ssl-redirect` and `force-ssl-redirect` are always on. The TLS secret name derives from the
**host**, not from the Ingress object, because a host served by several Ingress objects must
share one certificate — see [Exposure](exposure.md#one-certificate-per-host).

### PostgreSQL

Provisioned externally with CloudNativePG ([Prerequisites](prerequisites.md)). The charts only
address it.

| Key | Default |
|---|---|
| `global.postgres.host` | `ds-pg-rw.database.svc.cluster.local` |
| `global.postgres.port` | `5432` — also the port opened by the default-deny egress rule |
| `global.postgres.sslMode` | `require` |
| `global.postgres.databases.identityRegistry` | `identity_registry` |
| `global.postgres.databases.connectorPrefix` | `connector` → `connector_<participant>` |
| `global.postgres.databases.provenancePrefix` | `provenance` → `provenance_<participant>` |
| `global.postgres.databases.edcPrefix` | `edc` → `edc_<participant>` |

One database **and one least-privilege owner role** per service. The password never lands in a
ConfigMap or a rendered URL: the user and password come from the Secret and Kubernetes
interpolates them into the connection string.

### Keycloak

Externally managed; see [Keycloak requirements](keycloak.md).

| Key | Default | Notes |
|---|---|---|
| `global.keycloak.realm` | `dataspaces` | |
| `global.keycloak.issuerUrl` | — | **Required.** Under `DS_ENV=production` every service refuses to start without it |
| `global.keycloak.tokenUrl` | — | **Required.** `ds-edc` declares it required and its render fails without it |
| `global.keycloak.adminUrl` | — | used only by the optional sync init containers |
| `global.keycloak.sync.enabled` | `false` | opt-in provisioning of clients and organisations into the external realm |
| `global.keycloak.sync.clientsConfigMap` | `""` | a ConfigMap holding **`clients.effective.yaml`** — never the raw core file |
| `global.keycloak.sync.organizationsConfigMap` | `""` | a ConfigMap holding `organizations.yaml` |
| `global.keycloak.mutate` | `false` | may the registry write to the realm at *runtime* — creating a per-participant client at promotion and handing over its secret. Distinct from `sync` |
| `global.keycloak.aliases.groups` | `{}` | foreign group name → ds **bundle** name. Never a raw capability |
| `global.keycloak.aliases.owners` | `{}` | foreign organisation alias → ds owner id |

Both alias maps are emitted to **every** service that reads them, from this one block. That is
deliberate: a group map wired into some services and not others is a deployment where a caller's
authority depends on which service answered.

### Posture

| Key | Default | Notes |
|---|---|---|
| `global.networkPolicy.enabled` | `true` | default-deny ingress **and** egress |
| `global.monitoring.serviceMonitor` | `false` | also gates the `/metrics` NetworkPolicy |
| `global.monitoring.prometheusNamespace` | `monitoring` | the only namespace allowed to reach `/metrics` |
| `global.externalSecrets.enabled` | `false` | true → emit `ExternalSecret` CRs instead of `Secret`s |
| `global.externalSecrets.secretStoreRef` | `{}` | e.g. `{name: vault-backend, kind: ClusterSecretStore}` |
| `global.resources` | 100m/256Mi requests, 512Mi limit | per service unless overridden per chart |

`/metrics` is **unauthenticated** on the connector, provenance and the federated catalogue. It
is never routed through an Ingress, and the NetworkPolicy that permits scraping is rendered only
when `serviceMonitor` is enabled — so it is reachable from inside the cluster and nowhere else.
Treat that as containment, not authentication.

## `authority` — deploy once per dataspace

| Key | Default | Notes |
|---|---|---|
| `authority.enabled` | `true` | gates the whole release |
| `authority.identityRegistry.replicaCount` | `1` | migrations run as an init container; see [Replicas and migrations](#replicas-and-migrations) |
| `authority.identityRegistry.trustAnchorDomain` | `trust-anchor.ds.example.org` | must match `hosts.trustAnchor` + `baseDomain` |
| `authority.identityRegistry.exposeUserDids` | `false` | publish `users.<baseDomain>`; needed only when **remote** verifiers resolve your user DIDs |
| `authority.identityRegistry.credentialService.expose` | `false` | publish the DCP presentation-query endpoint; in the EDC flow the holder self-presents, so remote verifiers normally never call it |
| `authority.identityRegistry.bootstrap.enabled` | `true` | run the bootstrap and seed import as an init container |
| `authority.identityRegistry.bootstrap.seedConfigMap` | `""` | a ConfigMap with `agreements.yaml` / `owners.yaml`; empty → the image's baked-in defaults |
| `authority.identityRegistry.bootstrap.seedMountPath` | `/seed` | |

Bootstrap is idempotent by design — every command has upsert semantics — so it is safe on every
pod start. It runs `agreement import` → `owner import` → `org apply` **in that order**, because
an organisation inherits its capacity by accepting an agreement version, so the agreements must
exist first. `org apply` walks the full onboarding chain for every owner entry carrying a
dataspace block; entries without one are skipped rather than guessed at.

## `participants` — one release group each

A list. Each entry produces up to **six** releases named `ds-<service>-<name>`, in namespace
`<participantPrefix><name>`.

| Key | Default | Notes |
|---|---|---|
| `name` | — | **Required.** Also the participant's public host and DID: `did:web:<name>.<baseDomain>` |
| `enabled` | — | false → the whole group is skipped |
| `role` | — | `provider` or `consumer`; surfaces as a pod label and in service config |
| `did` | `""` | empty → derived. Override only to pin an existing DID |
| `datasetApi.url` | `""` | the dataset API is **participant-operated and external**; the charts only pass its URL |

### Per-service keys

| Key | Default | Notes |
|---|---|---|
| `connector.replicaCount` | `1` | |
| `connector.notifyBackends` | — | only `smtp` and `webhook` are real backend names; leave empty for no notifications |
| `connector.webhookAllowedHosts` | `[]` | SSRF guard. **An empty list rejects every webhook URL** — required if `notifyBackends` includes `webhook` |
| `connector.governanceOverlayName` | `""` | merges `governance.<name>.yaml` on top of the base file |
| `connector.governanceConfigMap` | `""` | supply the governance file from a ConfigMap |
| `provenance.replicaCount` | `1` | |
| `edc.replicaCount` | `1` | |
| `federatedCatalog.enabled` | per participant | **Crawling is a consumer-role operation** — a provider-role connector does not mount the route the crawler calls. Enable it on a consumer-role participant, or set `connectorServiceName` explicitly |
| `federatedCatalog.crawlInterval` | `300` | seconds |
| `portal.enabled` | per participant | the portal is deployed alongside exactly one participant, and brings `ds-oauth2-proxy` with it |
| `portal.replicaCount` | `1` | |

## Chart-level keys worth knowing

Not in `helm/values.yaml`. Settable per release by editing `helm/charts/<chart>/values.yaml`.

| Key | Chart | Default | Notes |
|---|---|---|---|
| `existingSecret` | all | `""` | reference a pre-created Secret; the chart then creates none |
| `migration.enabled` | Python services | `true` | Alembic `upgrade head` as an init container |
| `migration.mode` | Python services | `initContainer` | |
| `sqlSchemaAutocreate` | `ds-edc` | `true` | the EDC creates its own schema at boot — see [Prerequisites](prerequisites.md#one-database-and-one-role-per-service) |
| `didWebUseHttps` | `ds-edc` | `true` | **do not change.** Kept as a value only to make the invariant visible |
| `ports.*` | `ds-edc` | api 19191 · control 19192 · management 19193 · protocol 19194 | |
| `connectorServiceName` | `ds-edc`, `ds-federated-catalog` | `""` | empty → this participant's own connector |
| `credentialTtl.defaultDays` / `maxDays` | `ds-identity-registry` | 365 / 730 | issued-credential lifetime |
| `maxLineageDepth` | `ds-provenance` | `20` | |
| `auth.proxy.enabled` | `ds-portal` | `true` | fronts the portal with oauth2-proxy. **Disabling it does not fall back to a portal login — there is none**, so the portal is left open with client-controlled identity headers |
| `auth.serviceClientId` | `ds-portal` | `svc-ds-portal` | the portal's own service client |
| `auth.clientId` | `ds-oauth2-proxy` | `oauth2_proxy` | the realm's browser-login client |

### The connector's internal API and an external dataset API

In-cluster, the connector has no public Ingress and `/internal/*` is reachable only from the
same namespace. **If your dataset API runs outside the cluster, arrange connectivity
yourself** — run it in-namespace, or add a dedicated internal Ingress on which it presents its
own `svc-ds-dataset-api` Keycloak client credentials. Every caller of `/internal/*`
authenticates as itself; there is no shared API key.

## Replicas and migrations

Migrations run as an **init container**, one run per pod. With more than one replica, concurrent
runs serialise on Postgres locks rather than conflicting — Alembic's transactional DDL makes
this safe but not free. The charts default migration-carrying services to a single replica.

A `PodDisruptionBudget` with `minAvailable: 1` renders automatically whenever `replicaCount > 1`.
