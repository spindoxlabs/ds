# Operations

Install, upgrade, day-2 changes, and what to do when a deploy fails.

All commands run from `helm/`, with the SOPS key available:

```bash
cd helm
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

## Tooling

| Tool | Why |
|------|-----|
| `helm` ≥ 3.12 | chart rendering |
| `helmfile` v1 | release composition; reads `helmfile.yaml.gotmpl` |
| `helm-secrets` + `sops` + `age` | decrypts `secrets.sops.yaml` at render time |
| `kubeconform` (optional) | schema-validates the rendered manifests |

!!! warning "`helmfile.yaml.gotmpl`, never `helmfile.yaml`"
    Helmfile v1 only templates `{{ .Values.* }}` in the release list when the
    file carries the `.gotmpl` extension. Renaming it to plain `.yaml` fails with
    a cryptic map-key error.

## Install

```bash
# 1. Prerequisites — CNPG Cluster, Keycloak realm, cert-manager issuer, ingress
#    See Prerequisites and Keycloak requirements.

# 2. Configure
$EDITOR values.yaml                 # baseDomain, postgres, keycloak, participants
cp secrets.example.yaml secrets.sops.yaml
$EDITOR secrets.sops.yaml           # fill every CHANGE_ME
$EDITOR .sops.yaml                  # set your age or KMS recipient

# 3. Encrypt
sops --encrypt --in-place secrets.sops.yaml

# 4. Dry run, then apply
helmfile -e production diff
helmfile -e production apply
```

`helmDefaults` sets `wait: true`, `atomic: true` and `timeout: 600`, so a release
that fails to become ready rolls itself back rather than leaving the namespace
half-updated. Namespaces are **not** auto-created (`createNamespace: false`) —
they are owned by the `ds-namespaces` release, which also applies the labels the
NetworkPolicies match on.

### Order of operations

`needs` handles this, but it matters when something goes wrong: namespaces →
identity-registry → per participant (`ds-edc` → `ds-provenance` → `ds-connector`
→ catalog / portal). A participant's connector will not start before its EDC and
the authority registry are ready.

## Validate before you apply

```bash
# Re-resolve the ds-common library dependency after editing it
helm dependency update ./charts/ds-identity-registry

helm lint ./charts/ds-identity-registry \
  --set secrets.identityRegistryEncryptionKey=x \
  --set secrets.keycloakClientSecret=y \
  --set secrets.dbPassword=z

# Full render through SOPS — the real gate
helmfile -e production template

# Optional schema validation
helmfile -e production template | kubeconform -strict -summary
```

A successful full render proves every mandatory secret is wired, because the
Secret templates use `required`. A failed render names the missing key.

!!! note "`ds-common` is a `file://` dependency"
    After editing it, run `helm dependency update ./charts/<service>` (or delete
    `charts/<service>/charts/`) before re-rendering — otherwise you are testing a
    stale vendored copy.

## Upgrade

### Application version

```bash
$EDITOR values.yaml       # global.image.tag: "0.2.0"   (or a per-chart digest)
helmfile -e production diff
helmfile -e production apply
```

Database migrations run as an init container on each pod start
(`alembic upgrade head`), so a rolling update migrates before the new pods serve
traffic. Alembic tracks applied revisions, making this a no-op on an up-to-date
database.

Roll one participant at a time by narrowing the selector:

```bash
helmfile -e production -l name=ds-connector-provider apply
```

### Chart changes

`helmfile diff` before every apply. The Deployments carry a
`checksum/secret` annotation, so a secret change rolls the pods even when nothing
else in the spec moved — expect a restart in the diff when you rotate anything.

### Rollback

`atomic: true` rolls back a failed release automatically. To undo a successful
one:

```bash
helm -n ds-provider history ds-connector-provider
helm -n ds-provider rollback ds-connector-provider <revision>
```

Rolling back **does not roll back database migrations.** Alembic has no automatic
downgrade path here; treat a schema change as forward-only and roll forward with
a fix.

## Adding a participant

Four edits, all values-only, provided DNS already has a wildcard record:

1. **CNPG** — add three databases and three owner roles: `connector_<name>`,
   `provenance_<name>`, `edc_<name>`. See
   [`helm/docs/cnpg-cluster.example.yaml`](https://github.com/spindoxlabs/ds/blob/main/helm/docs/cnpg-cluster.example.yaml).
2. **`secrets.sops.yaml`** — three `postgres.*` passwords plus a
   `participants.<name>` block (`edcApiKey`, `edcVault.edrSigningPrivateJwk`,
   `stsSecret`). Generate the JWK with `task secrets:keygen`.
3. **`values.yaml`** — append an entry to `participants`.
4. **DNS/TLS** — `<name>.<baseDomain>` must resolve to the ingress controller. A
   wildcard record and wildcard certificate make this step a no-op.

```bash
sops secrets.sops.yaml          # edit in place, stays encrypted
helmfile -e production diff
helmfile -e production apply
```

The new participant's namespace, labels, releases and DID
(`did:web:<name>.<baseDomain>`) all derive from the entry. Register it in the
identity registry through the onboarding path — the charts create the workloads,
not the dataspace membership.

## Removing a participant

Set `enabled: false` on the entry and apply. Helmfile deletes the releases; the
namespace, its databases, and the registry entry survive deliberately —
provenance records and contract history outlive a participant's workloads. Clean
those up by hand once you are sure.

## Troubleshooting

### A pod refuses to start with a list of violations

Expected behaviour. `DS_ENV=production` puts every Python service's
`ProductionGuard` in fail-closed mode: it collects **all** violations in one
pass, logs them together, and exits. You get the complete list from a single
failed deploy rather than discovering them one rollout at a time.

```bash
kubectl -n ds-authority logs deploy/ds-identity-registry
```

Most common cause: `global.keycloak.issuerUrl` unset, or a secret left at a value
the guard recognises as a dev default (`admin`, `postgres`, `password`,
`changeme`, empty, or a service secret equal to its own client id).

### The render fails with `required` and a key name

The named secret has no value in `secrets.sops.yaml`. This is the design — the
chart will not deploy a default nobody chose.

### `helmfile` fails to decrypt

```bash
sops --decrypt secrets.sops.yaml >/dev/null   # isolate SOPS from helmfile
```

Check `SOPS_AGE_KEY_FILE`, and that `.sops.yaml` lists a recipient you hold the
private key for.

### Pod rejected by admission

Namespaces enforce Pod Security Admission `restricted`. A pod that violates it is
rejected by the API server. If it is one of these charts, the likely cause is a
non-numeric `runAsUser` — kubelet cannot verify `runAsNonRoot` against an image
whose `USER` is a name. All service Dockerfiles pin uid/gid **10001**; keep that
if you rework one.

### did:web does not resolve

```bash
curl -sf https://provider.$BASE_DOMAIN/.well-known/did.json | jq .id
```

Check, in order: DNS resolves to the ingress controller; the certificate is
issued (`kubectl get certificate -A`); exactly one Ingress per host carries the
`cluster-issuer` annotation; the `ExternalName` Service
`ds-edc-<participant>-identity-registry` exists in the participant namespace.

### A service cannot reach Keycloak or another service

Almost always NetworkPolicy. Confirm by temporarily setting
`global.networkPolicy.enabled: false` in a non-production environment — if the
call succeeds, the missing allow is the cause. See
[Exposure](exposure.md#networkpolicy-model), including the known 443-egress gap
on `ds-identity-registry` and `ds-provenance`.

### Certificate not issued

```bash
kubectl get certificate,certificaterequest,order,challenge -A
```

Competing Certificates for one secret means more than one Ingress on that host
carries the `cluster-issuer` annotation. Exactly one may.

### Migrations appear to hang with `replicaCount > 1`

Init containers run per pod, so concurrent migrations serialise on Postgres
locks. This is safe but slow. Keep migration-carrying services at one replica, or
scale up after the migration lands.

## Observability

`global.monitoring.serviceMonitor: true` renders the `ServiceMonitor` and the
NetworkPolicy that lets `global.monitoring.prometheusNamespace` scrape
`/metrics`. Those endpoints are unauthenticated and are never routed through an
Ingress.

Two gaps to close outside the charts, both required for NIS2 evidence:

- **Log shipping with a defined retention window.** Container logs are lost on
  restart without a cluster log shipper, and the Art. 23 notification deadlines
  cannot be evidenced without retained, searchable logs.
- **Keycloak audit events** (`eventsEnabled`, `adminEventsEnabled`,
  `adminEventsDetailsEnabled`) shipped to the same sink — an audit trail that
  expires inside Keycloak's own database is not evidence.

## Adding a service chart

1. `charts/ds-<svc>/` with `Chart.yaml` depending on `ds-common`
   (`file://../ds-common`).
2. A `templates/_env.tpl` mapping the service's `pydantic-settings` env prefix
   (grep `env_prefix=` in `services/<svc>/src/*/config.py`) onto values.
3. The standard object set: deployment, service, serviceaccount, secret,
   externalsecret, networkpolicy, pdb — and an ingress **only if**
   [Exposure](exposure.md) lists it.
4. A `global:` fallback block in the chart's `values.yaml` so it renders
   standalone under `helm lint`; real values arrive from `helm/values.yaml` via
   helmfile.
5. A release entry in `helmfile.yaml.gotmpl`, participant-scoped with
   `needs: [<authority ns>/ds-identity-registry]`.
6. Update the checklist in `helm/AGENTS.md` and this section.

All boilerplate belongs in `ds-common/templates/*.tpl` — naming, labels, image
composition, security contexts, the `DS_ENV` injection, secret-mode switching, DB
URL assembly, ingress TLS, probes, NetworkPolicy builders. A chart that
hand-rolls any of these is doing it wrong; extend a helper instead.

!!! note "Go-template comments cannot contain `*/`"
    A literal `*/` inside `{{/* … */}}` — a glob like `services/<star>/Dockerfile`,
    for instance — closes the comment early and breaks the parse. Reword.
