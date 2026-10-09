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
| `global.image.tag` | `""` | empty → each chart's `appVersion`, which **is** the release version |
| `global.image.pullPolicy` | `IfNotPresent` | |
| `global.image.pullSecrets` | `[]` | e.g. `[{name: ghcr-credentials}]` |

A per-chart `image.digest` wins over any tag. **Digest-pinning is the recommended production
form.**

### Choosing a release

The repository has one version. Cutting a release stamps it into every chart's `appVersion`
and publishes `ghcr.io/spindoxlabs/ds-<service>:<version>` — see
[Releasing](../development/releasing.md). So a checkout of tag `vX.Y.Z` deploys `X.Y.Z` with
nothing to configure.

To deploy a different release from the same checkout — a rollback, or a version bump you have
not merged the chart changes for — set `DS_IMAGE_TAG` instead of editing `values.yaml`:

```bash
DS_IMAGE_TAG=1.4.0 helmfile -e production apply
```

It overrides `global.image.tag` for every release in the helmfile at once. Overriding one
service alone is deliberately awkward: the services share internal contracts and are versioned
together.

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
| `global.keycloak.sync.clientsConfigMap` | `""` | a ConfigMap holding **every file that declares the realm** — `clients.dataspaces.yaml`, `clients.yaml` and each domain overlay; never a subset |
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
| `authority.identityRegistry.trustAnchorDomain` | `""` → `<hosts.trustAnchor>.<baseDomain>` | every participant derives the anchor's DID, trust list and status URL from `hosts.trustAnchor` + `baseDomain`; a literal here that differs **fails the render**, since the anchor would sign as a DID nobody trusts |
| `authority.identityRegistry.credentialService.expose` | `false` | publish the DCP presentation-query endpoint; in the EDC flow the holder self-presents, so remote verifiers normally never call it |
| `authority.identityRegistry.bootstrap.enabled` | `true` | run the bootstrap and seed import as an init container |
| `authority.identityRegistry.bootstrap.seedConfigMap` | `""` | a ConfigMap with `agreements.yaml` / `owners.yaml`; empty → the image's baked-in defaults |
| `authority.identityRegistry.bootstrap.seedMountPath` | `/seed` | |
| `authority.identityRegistry.bootstrap.seedItems` | `[]` | `{key, path}` pairs: the seed volume's own `items:`. A ConfigMap key cannot contain `/`, so an `agreements.yaml` whose `text:` paths are nested (`content/<doc>-<locale>.md`) is mounted by mapping each key back to its path. Listing items mounts **only** those |
| `authority.identityRegistry.bootstrap.governanceConfigMap` | `""` | a ConfigMap of governance files for `orgApply.governance`; its keys become flat filenames under the mount |
| `authority.identityRegistry.bootstrap.governanceMountPath` | `/governance` | |
| `authority.identityRegistry.bootstrap.orgApply.governance` | `[]` | governance files that choose which organisations to onboard; paths are relative to the mount unless absolute |
| `authority.identityRegistry.bootstrap.orgApply.verifiedBy` | `""` | who verified this run's entries. **Required** by the two keys around it |
| `authority.identityRegistry.bootstrap.orgApply.evidenceRef` | `""` | what that verification rests on, e.g. `env/prod/owners.yaml` |
| `authority.identityRegistry.bootstrap.orgApply.dryRun` | `false` | report and roll back instead of writing |

Bootstrap is idempotent by design — every command has upsert semantics — so it is safe on every
pod start. It runs `agreement import` → `owner import` → `org apply` **in that order**, because
an organisation inherits its capacity by accepting an agreement version, so the agreements must
exist first. `org apply` walks the full onboarding chain for every owner entry carrying a
dataspace block; entries without one are skipped rather than guessed at.

### Onboarding a deployment's own organisations

**A deployment's `owners.yaml` carries no `dataspace:` block on any entry, and its schema
forbids one** — that file is the deployment's domain registry, not a ds seed. So with
`orgApply` unset the bootstrap reads it, applies nothing and exits zero: a silent no-op, and
the default only because it is what this chart has always done.

`orgApply` is how a deployment stops it being one:

```yaml
authority:
  identityRegistry:
    bootstrap:
      governanceConfigMap: ds-governance
      orgApply:
        governance: [grid.yaml, rec_it.yaml]
        verifiedBy: example-dataspace-prod
        evidenceRef: env/prod/owners.yaml
```

`governance` decides **which** organisations: those owning a dataset the named files expose
into the dataspace (`dataspace.expose: true`), resolved to owners through the owners file's own
id/alias swap. Derived rather than listed, so the onboarded set cannot drift from the data
actually published. With `verifiedBy` alone and no `governance`, the selector is instead every
entry carrying a `did`.

`verifiedBy` / `evidenceRef` are **run-level** evidence — one claim for the whole invocation,
honest because what it rests on is this deployment's owners file at this revision. They apply
only where an entry supplies no evidence of its own: an owner already verified by something
else keeps its claim and is reported `verification: unchanged`, so re-running the bootstrap
never downgrades a real verification to a generic one.

The chain deliberately stops at a **verified owner holding its `did` and `aliases`** — which is
the whole of what `GET /owners/resolve` needs. No agreement is accepted, no credential issued
and no participant promoted: those are legal and topological facts a run-level flag must not
assert. See [the identity-registry service page](../services/identity-registry.md).

Two failure modes are made loud rather than silent:

- **`governance` or `evidenceRef` without `verifiedBy` fails at render**, before anything is
  applied. Without evidence every selected entry would be skipped and the run would report
  success having onboarded nobody.
- **A governance file naming an owner the deployment does not declare, or one that carries no
  DID, fails the whole run** — every such owner reported in one pass, so a fourteen-owner file
  is fixed once. Set `dryRun: true` to get that report against the committed files without
  writing, which is what makes a deployment reviewable before it is applied.

## `participants` — one release group each

A list. Each entry produces up to **six** releases named `ds-<service>-<name>`, in namespace
`<participantPrefix><name>`.

| Key | Default | Notes |
|---|---|---|
| `name` | — | **Required.** Also the participant's public host and DID: `did:web:<name>.<baseDomain>` |
| `enabled` | — | false → the whole group is skipped |
| `role` | — | `provider`, `consumer` or `both` (one connector process, both routers, one EDC); surfaces as a pod label and in service config |
| `did` | `""` | empty → derived. Override only to pin an existing DID |

The dataset API takes no key here. It is participant-operated and external, and
the charts have nothing to tell it: it calls the connector at
`/internal/dataplane/authorize`, not the other way round, and where a consumer
is sent for data is the asset's `data_address.base_url` in `governance.yaml`.
It runs in the host platform's namespace, so the connector must admit it:
`connector.networkPolicy.ingressFrom`, below.

**`helm/values.yaml` lists no participants.** A deployment lists its own in its own
values; helmfile merges a list over a list element by element, so a list in the
base would leak into every deployment. ds's example participants are in
`helm/values.example.yaml`, read only by `helmfile -e example`.

### Per-service keys

**A participant's `connector`, `edc`, `provenance` and `portal` blocks are those
charts' values, forwarded whole** — every key in `helm/charts/<chart>/values.yaml`
is settable here. `secrets`, `participant`, `global` and `existingSecret` are refused
in them (secrets come from the secrets file, identity from the participant entry).
The flat spellings used before (`connector.governanceConfigMap`,
`.governanceOverlayName`, `.notifyBackends`, `.webhookAllowedHosts`) fail the render
naming the new key. The ones a deployment sets:

| Key | Default | Notes |
|---|---|---|
| `connector.replicaCount` | `1` | |
| `connector.clientId` | `svc-ds-connector-<name>` | the organisation client this connector — and its sync Job — authenticates as. Set it when the participant's name differs from the organisation's alias in the realm. Its secret is `participants.<name>.organisationClientSecret` in the secrets file, and must equal what the realm holds ([Secrets](secrets.md)) |
| `connector.notify.backends` | `""` | only `smtp` and `webhook` are real backend names; empty for no notifications |
| `connector.notify.webhookAllowedHosts` | `[]` | SSRF guard. **An empty list rejects every webhook URL** — required if `backends` includes `webhook` |
| `connector.governance.configMap` | `""` | the governance files, from a ConfigMap the deployment builds. Empty → no governance, empty catalogue |
| `connector.governance.overlayName` | `""` | merges `governance.<name>.yaml` on top of the base file |
| `connector.governance.odrlProfileFile` | `""` | the deployment's own ODRL profile, a key of that ConfigMap → `CONNECTOR_ODRL_PROFILE_PATH`. Unset, ds's bundled profile is used and **every offer naming a deployment-added purpose stops publishing** |
| `connector.governance.checksum` | `""` | a digest of what the deployment assembled. Rendered as the pod annotation `checksum/governance`, so a governance change is a rollout and the sync hook re-runs; without it a rebuilt ConfigMap with unchanged values changes nothing |
| `connector.networkPolicy.ingressFrom` | `[]` | `{namespace, podLabels}` entries admitted to the connector's port — the host platform's consent writer and data plane. `namespace` is required; with `podLabels`, only those pods. See [Exposure](exposure.md) |
| `connector.sync.clientId` | `""` | publish as a separate client (`svc-ds-publisher`); its secret is `participants.<name>.publisherSecret` |
| `connector.personTokenRequired`, `connector.trustAnchor.*`, `connector.podAnnotations` | | as in the chart; see below |
| `provenance.replicaCount` | `1` | `provenance.personTokenRequired` and `.trustAnchor.*` as for the connector |
| `edc.replicaCount` | `1` | `edc.managementAudience`, `edc.edrPublicBaseUrl` likewise |
| `federatedCatalog.enabled` | per participant | **Crawling is a consumer-role operation** — a provider-role connector does not mount the route the crawler calls. Enable it where a participant of role `consumer` or `both` exists (the crawl uses the first such connector), or set `connectorServiceName` explicitly |
| `federatedCatalog.crawlInterval` | `300` | seconds |
| `portal.enabled` | per participant | the portal is deployed alongside exactly one participant, and brings `ds-oauth2-proxy` with it |
| `portal.replicaCount` | `1` | |
| `portal.datasetApi.url` | `""` | the catalogue page's source when the participant runs no federated catalogue (`CATALOGUE_URL`) |
| `portal.consumer.*` | `""` | `defaultAssigner`, `defaultCounterPartyAddress`: the provider the portal's consumer flow defaults to |

The portal names its federated catalogue (`FEDERATED_CATALOG_URL`) only when
`federatedCatalog.enabled` is true for the same participant; otherwise it falls back
to `portal.datasetApi.url`.

## Chart-level keys worth knowing

Not in `helm/values.yaml`. Settable for a participant's releases through its forwarded
blocks (above); the anchor's through `authority.identityRegistry`.

| Key | Chart | Default | Notes |
|---|---|---|---|
| `existingSecret` | all | `""` | reference a pre-created Secret; the chart then creates none |
| `migration.enabled` | Python services | `true` | Alembic `upgrade head` as an init container |
| `migration.mode` | Python services | `initContainer` | |
| `sqlSchemaAutocreate` | `ds-edc` | `true` | the EDC creates its own schema at boot — see [Prerequisites](prerequisites.md#one-database-and-one-role-per-service) |
| `didWebUseHttps` | `ds-edc` | `true` | **do not change.** Kept as a value only to make the invariant visible |
| `ports.*` | `ds-edc` | api 19191 · control 19192 · management 19193 · protocol 19194 | management is in-cluster only, and must stay so ([ADR-0014](../decisions/ADR-0014-management-api-v5-and-the-organisation-actor.md)); the runtime also requires `ds.management.audience` (`svc-ds-edc`) and refuses to boot without it |
| `edc.managementApiVersion` | `ds-connector` | `v5beta` | the management API path segment; `v5` from EDC 0.19 |
| `sync.clientId` | `ds-connector` | `""` → the organisation client | who the post-install sync job publishes as. As the organisation client it requests `scope=connector.provider.write`, which is optional on that client ([ADR-0026](../decisions/ADR-0026-an-organisation-acts-through-its-collector-client-one-audience-per-scope.md)). Naming a client such as `svc-ds-publisher`, which holds the grant by default, switches the job to `secrets.publisherSecret` and requests no scope |
| `keycloak.sync.organisationClientSecrets` | `ds-identity-registry` | `""` | a Secret holding `SVC_DS_CONNECTOR_<ALIAS>_SECRET` for each organisation with a participant context, and `SVC_DS_COLLECTOR_<ALIAS>_SECRET` for each organisation that declares `collects_consent` (its collector client, which the onboarding service authenticates as). `org-sync` refuses a client whose secret is missing outside `DS_ENV=dev` |
| `connectorServiceName` | `ds-edc`, `ds-federated-catalog` | `""` | empty → this participant's own connector |
| `credentialTtl.defaultDays` / `maxDays` | `ds-identity-registry` | 365 / 730 | issued-credential lifetime |
| `trustAnchor.credentialStatusUrl` | `ds-connector`, `ds-provenance` | `""` → `https://<trustAnchor host>.<baseDomain>/status/1` | the anchor's status registers. **Required**: the service refuses to start without it. Read as the anchor's signed VC-JWT; it pins the origin, and each credential names its own register and bit |
| `trustAnchor.credentialStatusCacheSeconds` | `ds-connector`, `ds-provenance` | `""` (service default 900) | how long a verified register is reused, which is the **revocation latency** |
| `personTokenRequired` | `ds-connector`, `ds-provenance` | `""` (required) | person routes take the person's own login token, bound to their credential ([ADR-0024](../decisions/ADR-0024-a-person-route-takes-the-persons-login.md)). `false` is a transition switch for a caller that does not forward the token yet, and is logged at startup |
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

### Key assertions, the release link and the key-record retention (connector `0016`)

[ADR-0027](../decisions/ADR-0027-the-collector-asserts-whose-keys-it-registers.md). Four
things a deployment decides or orders:

- **Which offers require a collector's key assertion.** Declare it on the holder's sharing
  offers (`key_assertion: required`, or `{required, methods}`). An offer that declares
  nothing requires one for a `pod:` key outside `DS_ENV=dev` anyway; declaring it makes the
  holder's choice visible in its own governance.
- **Upgrade order.** ds-provenance first (it must know `KeySuspension` and the new digest
  fields), then the data plane (it must accept `decision_ref` in the authorize answer —
  `extra="forbid"`), then the connector. The collector (the onboarding service) sends the
  assertion before the holder's connector requires it.
- **Migration `0016` can stop.** It backfills one owner per `pod:` key a grant carries and
  refuses to run when a key is carried by two subjects' grants at this holder. Have the
  collector withdraw the wrong registration, then migrate again. The downgrade deletes ledger
  entries whose decision row is gone, which the `0015` schema cannot hold.
- **The retention period.** `CONNECTOR_KEY_RECORD_RETENTION_DAYS` (default `3650`, the Italian
  ordinary limitation period, **pending legal counsel**). Only the purge reads it, and the
  chart does not template it: set it in the environment of the purge run. Nothing deletes the
  key records on a schedule; after the period an operator runs
  `python -m connector.db.retention purge` in the connector image (a dry run), then again with
  `--apply`. The basis for keeping them after a subject's erasure is GDPR Art. 17(3)(e); record
  the period your deployment chose in its own agreement text.

## Replicas and migrations

Migrations run as an **init container**, one run per pod. With more than one replica, concurrent
runs serialise on Postgres locks rather than conflicting — Alembic's transactional DDL makes
this safe but not free. The charts default migration-carrying services to a single replica.

A `PodDisruptionBudget` with `minAvailable: 1` renders automatically whenever `replicaCount > 1`.
