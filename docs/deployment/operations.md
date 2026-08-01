# Operations

Install, upgrade, day-2 changes, and what to do when a deploy fails.

All commands run from `helm/`, with the SOPS key available:

```bash
cd helm
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

## Tooling

| Tool | Why |
|---|---|
| `helm` ≥ 3.12 | chart rendering |
| `helmfile` v1 | release composition |
| `helm-secrets` + `sops` + `age` | decrypts `secrets.sops.yaml` at render time |
| `kubeconform` (optional) | schema-validates the rendered manifests |

!!! warning "`helmfile.yaml.gotmpl`, never `helmfile.yaml`"
    Helmfile v1 only templates `{{ .Values.* }}` in the release list when the file carries the
    `.gotmpl` extension. Renaming it to plain `.yaml` fails with a cryptic map-key error.

## Install

```bash
# 1. Prerequisites — a CNPG Cluster, a Keycloak realm, a cert-manager issuer, an ingress
#    controller. See Prerequisites and Keycloak requirements.

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

`helmDefaults` sets `wait`, `atomic` and a 600-second timeout, so a release that fails to become
ready **rolls itself back** rather than leaving the namespace half-updated.

Namespaces are **not** auto-created — they are owned by the `ds-namespaces` release, which also
applies the labels the NetworkPolicies match on.

### Order of operations

`needs` handles this, but it matters when something goes wrong:

```
namespaces → identity-registry → per participant:
    ds-edc, ds-provenance → ds-connector → ds-federated-catalog / ds-oauth2-proxy → ds-portal
```

A participant's connector will not start before its EDC and the authority registry are ready,
and the portal will not start before its oauth2-proxy — **an Ingress whose `auth-url` backend
does not resolve fails closed**, so every request would 500.

## Validate before you apply

```bash
# re-resolve the shared library chart after editing it
helm dependency update ./charts/ds-identity-registry

helm lint ./charts/ds-identity-registry \
  --set secrets.identityRegistryEncryptionKey=x \
  --set secrets.keycloakClientSecret=y \
  --set secrets.dbPassword=z

# full render through SOPS — the intended gate
helmfile -e production template

# optional schema validation
helmfile -e production template | kubeconform -strict -summary
```

A successful full render proves every mandatory secret is wired, because the Secret templates
use `required`. A failed render names the missing key.

!!! note "`ds-common` is a `file://` dependency"
    After editing it, run `helm dependency update ./charts/<service>` (or delete the vendored
    `charts/<service>/charts/`) before re-rendering — otherwise you are testing a stale copy.

## Upgrade

### Application version

```bash
$EDITOR values.yaml       # global.image.tag: "0.2.0"   (or a per-chart digest)
helmfile -e production diff
helmfile -e production apply
```

Database migrations run as an init container on each pod start, so a rolling update migrates
before the new pods serve traffic. Alembic tracks applied revisions, making this a no-op on an
up-to-date database.

Roll one participant at a time by narrowing the selector:

```bash
helmfile -e production -l name=ds-connector-provider apply
```

### Chart changes

`helmfile diff` before every apply. The Deployments carry a `checksum/secret` annotation, so a
secret change rolls the pods even when nothing else in the spec moved — expect a restart in the
diff when you rotate anything.

### Rollback

`atomic` rolls back a failed release automatically. To undo a successful one:

```bash
helm -n ds-provider history ds-connector-provider
helm -n ds-provider rollback ds-connector-provider <revision>
```

!!! warning "Rolling back does not roll back database migrations"
    Alembic has no automatic downgrade path here. Treat a schema change as forward-only and roll
    forward with a fix.

### Upgrading past identity-registry schema 0011 — credentials may need re-issuing

Before 0011, the identity registry allocated a credential's StatusList index by scanning the
**revocation register** for its first unset bit. That register records which credentials are
revoked, so it cannot also allocate: four issuance paths left the bit clear, which meant the
scan never advanced and consecutive credentials were issued the *same* index; two set it, which
allocated correctly but published those credentials revoked from birth.

The consequence for a deployment carrying credentials issued before 0011: **revoking any one of
a colliding group revokes all of them.**

The 0011 migration fixes allocation and prints any collisions it finds, but it cannot repair
them, and it does not block the upgrade — refusing would only strand you on the code that
causes the problem. `status_list_index` is inside the **signed** credential JSON, so changing it
invalidates the signature. Affected credentials can only be **re-issued**.

Check any environment before and after upgrading:

```bash
kubectl -n ds-provider exec deploy/ds-identity-registry -- ir-cli status check-indices
```

It exits non-zero and names every affected credential and subject when there are collisions, so
it can gate a deployment. The service also logs the same summary on every start.

Re-issue the credentials it names through the normal path for their type — `ir-cli credential
issue-membership`, `issue-data-subject`, or the organisation onboarding chain — and revoke the
old ones **after** the replacements are distributed, since revoking first takes down the whole
colliding group. In development the whole remedy is `ir-cli bootstrap`.

## Adding a participant

Four edits, all values-only, provided DNS already has a wildcard record:

1. **CNPG** — add three databases and three owner roles: `connector_<name>`,
   `provenance_<name>`, `edc_<name>`.
2. **`secrets.sops.yaml`** — three Postgres passwords plus a `participants.<name>` block
   (`edcApiKey`, `edcVault.edrSigningPrivateJwk`, `stsSecret`). Generate the JWK with
   `task secrets:keygen`.
3. **`values.yaml`** — append an entry to `participants`.
4. **DNS/TLS** — `<name>.<baseDomain>` must resolve to the ingress controller. A wildcard record
   and wildcard certificate make this a no-op.

```bash
sops secrets.sops.yaml          # edit in place, stays encrypted
helmfile -e production diff
helmfile -e production apply
```

The new participant's namespace, labels, releases and DID all derive from the entry. **Register
it in the identity registry through the onboarding path** — the charts create the workloads, not
the dataspace membership.

## Removing a participant

Set `enabled: false` on the entry and apply. Helmfile deletes the releases; **the namespace, its
databases and the registry entry survive deliberately** — provenance records and contract
history outlive a participant's workloads. Clean those up by hand once you are sure.

## Troubleshooting

### A pod refuses to start with a list of violations

Expected behaviour. `DS_ENV=production` puts every Python service's startup guard in fail-closed
mode: it collects **all** violations in one pass, logs them together, and exits. You get the
complete list from a single failed deploy rather than discovering them one rollout at a time.

```bash
kubectl -n ds-authority logs deploy/ds-identity-registry
```

Most common cause: `global.keycloak.issuerUrl` unset, or a secret left at a value the guard
recognises as a dev default (`admin`, `postgres`, `password`, `changeme`, empty, or a service
secret equal to its own client id).

### The render fails with `required` and a key name

The named secret has no value in `secrets.sops.yaml`. This is the design — the chart will not
deploy a default nobody chose.

### helmfile fails to decrypt

```bash
sops --decrypt secrets.sops.yaml >/dev/null   # isolate SOPS from helmfile
```

Check `SOPS_AGE_KEY_FILE`, and that `.sops.yaml` lists a recipient you hold the private key for.

### A pod is rejected by admission

Namespaces enforce Pod Security Admission `restricted`. The likely cause is a non-numeric
`runAsUser` — kubelet cannot verify `runAsNonRoot` against an image whose `USER` is a name. All
service Dockerfiles pin uid/gid **10001**; keep that if you rework one.

### `did:web` does not resolve

```bash
curl -sf https://provider.$BASE_DOMAIN/.well-known/did.json | jq .id
```

Check, in order: DNS resolves to the ingress controller; the certificate is issued
(`kubectl get certificate -A`); exactly one Ingress per host carries the cluster-issuer
annotation; the `ExternalName` Service pointing at the authority registry exists in the
participant namespace.

### A service cannot reach Keycloak or another service

Almost always NetworkPolicy. Confirm by temporarily disabling `global.networkPolicy.enabled` in
a non-production environment — if the call succeeds, the missing allow is the cause. Add it with
`.Values.networkPolicy.egress` on the release rather than by editing a template; see
[Exposure](exposure.md#opening-a-path-the-chart-does-not-know-about).

### A certificate is not issued

```bash
kubectl get certificate,certificaterequest,order,challenge -A
```

Competing Certificates for one secret means more than one Ingress on that host carries the
cluster-issuer annotation. Exactly one may.

### Migrations appear to hang with more than one replica

Init containers run per pod, so concurrent migrations serialise on Postgres locks. This is safe
but slow. Keep migration-carrying services at one replica, or scale up after the migration
lands.

## Observability

`global.monitoring.serviceMonitor: true` renders the `ServiceMonitor` and the NetworkPolicy that
lets the Prometheus namespace scrape `/metrics`. Those endpoints are unauthenticated and are
never routed through an Ingress.

Two things to arrange outside the charts:

- **Log shipping with a defined retention window.** Container logs are lost on restart without a
  cluster log shipper, and incident-notification deadlines cannot be evidenced without retained,
  searchable logs.
- **Keycloak audit events** shipped to the same sink — an audit trail that expires inside
  Keycloak's own database is not evidence.

## Adding a service chart

1. `charts/ds-<svc>/` with a `Chart.yaml` depending on `ds-common` (`file://../ds-common`).
2. A `templates/_env.tpl` mapping the service's settings prefix onto values.
3. The standard object set: deployment, service, serviceaccount, secret, externalsecret,
   networkpolicy, pdb — and an Ingress **only if** [Exposure](exposure.md) lists it.
4. A `global:` fallback block in the chart's own `values.yaml` so it renders standalone under
   `helm lint`; real values arrive from `helm/values.yaml` via helmfile.
5. A release entry in `helmfile.yaml.gotmpl`, participant-scoped, needing the authority registry.
6. Update this section and the checklist in `helm/AGENTS.md`.

All boilerplate belongs in `ds-common` — naming, labels, image composition, security contexts,
the `DS_ENV` injection, secret-mode switching, database URL assembly, ingress TLS, probes,
NetworkPolicy builders. **A chart that hand-rolls any of these is doing it wrong**; extend a
helper instead.

!!! note "Go-template comments cannot contain `*/`"
    A literal `*/` inside `{{/* … */}}` — a glob like `services/<star>/Dockerfile`, for
    instance — closes the comment early and breaks the parse. Reword.
