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

From the deployment's own repository, whose helmfile takes ds's as its base (see
`helm/README.md`, *Install — from your own repository*, for the parent helmfile):

```bash
# 1. Prerequisites — CNPG roles and databases, the Keycloak realm's clients, a
#    cert-manager issuer, an ingress controller. See Prerequisites and Keycloak.

# 2. Configure, in the deployment repository
$EDITOR overlay/staging/values.yaml          # baseDomain, namespaces, keycloak, participants
$EDITOR overlay/staging/secrets.sops.yaml    # every key of ds/helm/secrets.example.yaml (sops)

# 3. Preflight the decrypted secrets (never prints a value)
sops -d overlay/staging/secrets.sops.yaml > secrets.dec.yaml
task -d ds secrets:check FILE=$PWD/secrets.dec.yaml; rm secrets.dec.yaml

# 4. Dry run, apply, then the content checks
helmfile -e staging diff
helmfile -e staging apply
helm test -n <participant namespace> ds-edc-<participant>     # and each release below
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

### Who publishes

`POST /provider/sync` is what turns a participant's assembled `governance.yaml`
into EDC assets, policies and contract definitions. Nothing else does: a provider
can be installed, healthy, registered and reachable with an **empty catalogue**,
and no probe reports it. A deployment ran that way for a fortnight because this
page did not say who makes the call and the charts had no job that made it.

The `ds-connector` chart carries one now — a `post-install`/`post-upgrade` hook
Job, rendered only for a **provider-role** participant that has
`governance.configMap` set. It fails the release when the sync reports errors or
publishes nothing, and it reads the body rather than the status code.

Two identities may make the call, and the choice is a real one:

| | When |
|---|---|
| the participant's **organisation client** (`svc-ds-connector-<alias>`) | the default. It already exists, it is already in the release's Secret, and the connector binds it to its own participant. Self-service publishing |
| **`svc-ds-publisher`** | set `sync.clientId` and `secrets.publisherSecret`. It holds `connector.provider.read` + `.write` and **no** `management-api:*`, so a credential that drives a deployment cannot also administer that participant's contracts through the EDC management API (ADR-0014 decision 3 makes port reachability the only control there) |

Prefer the publisher wherever the credential is handled outside the cluster — a
CI job, a bootstrap script, an operator's terminal. Prefer the organisation
client where the publish is the participant's own act.

The hook runs on every `helmfile apply`, which is how a governance change reaches
the catalogue: update the ConfigMap and apply. A sync is idempotent, and because
it **reconciles**, applying also removes what governance no longer declares — see
[the connector's page](../services/connector.md#what-the-sync-removes). The Job's
log names what was published and what was withdrawn.

## Validate before you apply

```bash
task helm:test                  # in ds: lint, the example render, the pilot-shaped render
helmfile -e staging template    # in the deployment repository: the real values, the real gate
helmfile -e staging template | kubeconform -strict -summary   # optional schema validation
```

A successful render proves every mandatory secret is wired (the Secret templates use
`required`) **and** that the secret policy holds: no placeholder or dev default, no custody key
shared, `svc-edc`'s secret equal everywhere, the EDR key halves agreeing, one trust-anchor host.
A failed render names the key, never the value.

## After an install or upgrade: `helm test`

| Release | What it asserts |
|---|---|
| `ds-edc-<p>` | the participant host serves the DID document through the Ingress, `id` = the participant's DID |
| `ds-identity-registry-<p>` | the participant registry answers in-cluster and holds that DID document |
| `ds-connector-<p>` | the catalogue, read as the organisation client, is non-empty and as large as the governance's exposed set |
| `ds-portal-<p>` | through the Ingress, with no session, `/join` is 200 and `/` is not |

A failed test Pod is kept (`before-hook-creation`), so `kubectl logs` says why. The rows the
local doctor checks that read systems ds does not deploy — the data plane, the node's own
catalogue, the gold-only gate — stay the deployment's checks.

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
helmfile -e production -l name=ds-connector-rec apply
```

### Chart changes

`helmfile diff` before every apply. The Deployments carry a `checksum/secret` annotation, so a
secret change rolls the pods even when nothing else in the spec moved — expect a restart in the
diff when you rotate anything.

### A governance change is a checksum change

The governance ConfigMap is the deployment's, built outside these charts. Rebuilding it with
unchanged chart values changes nothing helmfile can see: no rollout, and the connector's
post-upgrade sync does not run, so the catalogue keeps offering the old governance. Pass a
digest of what you assembled as `connector.governance.checksum`; it is the pod annotation
`checksum/governance`, so the change is a rollout and the sync hook publishes it.

### The data plane first, then the connector

The row-filter contract between the connector (the decision point) and the data plane (the
enforcement point) is strict on both sides (`extra="forbid"`), so a connector that sends a field
the deployed data plane does not know is refused, not misread. Upgrade the data plane first,
then the connector, then check the data plane's own doctor row.

### Rollback

`atomic` rolls back a failed release automatically. To undo a successful one:

```bash
helm -n ds-provider history ds-connector-rec
helm -n ds-provider rollback ds-connector-rec <revision>
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

### Upgrading past connector schema 0012 — consent is registered by an organisation client

**Breaking, for any service that calls `POST /consent/admin/shares`.** From this version the
connector refuses a plain service token there (`403`, naming the client to use). Consent is
registered by an **organisation's own client** — `svc-ds-connector-<alias>`, the client
`ir-cli keycloak org-sync` and the provisioning bundle create — or, for the evidenced
`override_subject_withdrawal` alone, by a person holding `connector.admin`.

What a deployment has to do, in this order:

1. **Give the caller its organisation's client.** An onboarding service that registers consent
   for a community's members authenticates as that community's `svc-ds-connector-<alias>` with
   the secret `SVC_DS_CONNECTOR_<ALIAS>_SECRET`. It needs no new permission: the client already
   holds `connector.consent.provision` (`ds_auth.CONNECTOR_SERVICE_SCOPES`).
2. **Say whose decision it is.** An organisation token must send `decided_by`:
   `"subject"` when it relays a decision the member took, `"collector"` when the organisation
   decided itself. A relayed withdrawal then belongs to the member and nothing else lifts it
   (`D-15c`).
3. **Register at the connector that holds the data.** Writing at *another* participant's
   connector also needs that participant to accept the organisation as a consent collector:
   `ir-cli collector add --holder-did … --collector-did …` on the trust anchor, or
   `POST /admin/consent-collectors`. The subject must be a member of the *writing*
   organisation.

   **Revoking and reinstating a collector.** `ir-cli collector revoke --holder-did …
   --collector-did … --reason "…" [--by <who>]` stops the collector writing; the consents it
   already registered stay. The revocation **survives** the anchor's bootstrap: a seed that runs
   `collector add` on every start (the charts' `bootstrap.sh`) leaves a revoked pair revoked
   and logs `Consent collector revoked, left unchanged: … (revoked by … at …: …)`. So a
   revocation needs no edit to the seed, and removing the pair from the seed revokes nothing.
   To put it back in force: `ir-cli collector reinstate --holder-did … --collector-did …
   --reason "…" [--by <who>]` (or `POST /admin/consent-collectors/reinstate`), which checks the
   add's preconditions again and records who, when and why on the row.
4. **Drop the old grant.** `connector.consent.provision` is no longer useful on a plain service
   client (`svc-ds-onboarding` in `services/keycloak/clients.yaml` no longer carries it), and it
   is no longer in the `ds-participant-admin` bundle, so a participant operator's console cannot
   register consent either.

Nothing has to be migrated in the database: rows written by the retired path keep
`decided_by = "service"`, and the holder's own organisation client (or its operator) may still
lift the withdrawals among them.

## Adding a participant

Values-only, in the deployment repository, provided DNS already has a wildcard record:

1. **CNPG** — four databases and owner roles: `identity_registry_<name>`, `connector_<name>`,
   `provenance_<name>`, `edc_<name>` (`-` in the name becomes `_`).
2. **The secrets file** — four Postgres passwords plus a `participants.<name>` block: every key
   `helm/secrets.example.yaml` shows for one participant, including the EDR key pair
   (`edcVault.edrSigningPrivateJwk` and its public half `edrSigningPublicJwk`, from
   `task secrets:keygen`). `connectorClientSecret` is the same `svc-edc` secret every
   participant has; every other key is this participant's own.
3. **The values file** — append an entry to `participants`.
4. **DNS/TLS** — `<name>.<baseDomain>` must resolve to the ingress controller. A wildcard record
   and wildcard certificate make this a no-op.

```bash
helmfile -e staging diff
helmfile -e staging apply
```

The new participant's namespace, labels, releases and DID all derive from the entry.

### Enrolment — an operator step

The participant registry generates its own key and publishes its DID document at every start,
but **does not enrol itself**: enrolment spends a single-use code, and a code in a Deployment
would be replayed at every restart. So it is two commands, run once by an operator:

```bash
# 1. at the anchor: mint a code for the organisation's owner alias
kubectl -n <authority namespace> exec deploy/ds-identity-registry -- \
  ir-cli org enrolment-token --alias <owner alias> --label "<who it went to>"
# 2. in the participant's own registry pod: spend it, unless already enrolled
kubectl -n <participant namespace> exec deploy/ds-identity-registry-<name> -- \
  sh -c 'ir-cli participant status --quiet || ir-cli participant init --code "<code>"'
```

The anchor verifies the enrolment by fetching the participant's DID document over did:web, so
the participant host must already serve it (`helm test ds-edc-<name>`).

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
annotation; the participant's own identity-registry release
(`ds-identity-registry-<participant>`) is running in the participant namespace — the DID
document is served by it, not by the trust anchor.

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
2. A `helm/charts/<chart>/templates/_env.tpl` mapping the service's settings prefix onto values.
3. The standard object set: deployment, service, serviceaccount, secret, networkpolicy,
   pdb — and an Ingress **only if** [Exposure](exposure.md) lists it.
4. A `global:` fallback block in the chart's own `values.yaml` so it renders standalone under
   `helm lint`; real values arrive from `helm/values.yaml` via helmfile.
5. A release entry in `helmfile.yaml.gotmpl`, participant-scoped, needing the authority registry.
6. Update this section, and [Exposure](exposure.md) if the unit gets a public path.

All boilerplate belongs in `ds-common` — naming, labels, image composition, security contexts,
the `DS_ENV` injection, secret-mode switching, database URL assembly, ingress TLS, probes,
NetworkPolicy builders. **A chart that hand-rolls any of these is doing it wrong**; extend a
helper instead.

!!! note "Go-template comments cannot contain `*/`"
    A literal `*/` inside `{{/* … */}}` — a glob like `services/<star>/Dockerfile`, for
    instance — closes the comment early and breaks the parse. Reword.
