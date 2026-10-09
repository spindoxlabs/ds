# Dataspace Helm deployment

Charts and helmfile for deploying the dataspace to Kubernetes.

**The operator documentation is published as the Deployment section of the docs
site** and lives in [`docs/deployment/`](../docs/deployment/):

| Page | |
|------|--|
| [Overview](../docs/deployment/index.md) | what deploys, topology, release graph |
| [Prerequisites](../docs/deployment/prerequisites.md) | CloudNativePG, Keycloak, cert-manager, ingress, DNS |
| [Keycloak requirements](../docs/deployment/keycloak.md) | the realm contract these charts consume |
| [Configuration reference](../docs/deployment/configuration.md) | `values.yaml`, key by key |
| [Secrets](../docs/deployment/secrets.md) | delivery modes, key reference, rotation |
| [Exposure and network policy](../docs/deployment/exposure.md) | public surface, NetworkPolicies, PSA |
| [Operations](../docs/deployment/operations.md) | install, upgrade, day-2, troubleshooting |

In this folder:

- **CNPG reference manifest:** [`docs/cnpg-cluster.example.yaml`](./docs/cnpg-cluster.example.yaml)

## What deploys

| Group | Releases | Cardinality |
|-------|----------|-------------|
| authority | `ds-identity-registry` | once per dataspace |
| participant | `ds-edc`, `ds-connector`, `ds-provenance`, `ds-federated-catalog`, `ds-oauth2-proxy`, `ds-portal` | once per participant |

Postgres (CloudNativePG), Keycloak and cert-manager are **not** installed by
these charts — see [Prerequisites](../docs/deployment/prerequisites.md). The
dev-only `dataset-api-mock`, `caddy` and `edc-extensions` are intentionally
excluded.

> **Status:** all eight charts are implemented — `ds-common` (library),
> `ds-namespaces`, the authority `ds-identity-registry`, and the participant
> tier `ds-edc` / `ds-connector` / `ds-provenance` / `ds-federated-catalog` /
> `ds-oauth2-proxy` / `ds-portal`.
>
> `ds-oauth2-proxy` is not optional wherever `ds-portal` is deployed: the portal
> is no longer an OIDC client, so without it the human-facing host has no login
> in front of it and the identity headers it reads are client-controlled. The full `helmfile.yaml.gotmpl` composes an authority plus any
> number of participants, as the base of a deployment's own helmfile.

## Install — from your own repository

**ds is a public repository, so a deployment's values and its encrypted secrets
live in the deployment's own repository, never here.** That repository has its
own helmfile, which takes this one as its base (`every-secret-has-one-source`,
M1), its own sops setup, and one values and one secrets file per environment:

```yaml
# <your deployment>/helmfile.yaml.gotmpl
environments:
  staging:                       # must be an environment ds declares: staging | production
    values:
      - overlay/staging/values.yaml        # baseDomain, namespaces, keycloak, participants
    secrets:
      - overlay/staging/secrets.sops.yaml  # every key of helm/secrets.example.yaml
---
helmfiles:
  - path: ds/helm/helmfile.yaml.gotmpl     # ds as a submodule, pinned to a release tag
    values:
      - {{ toYaml .Values | nindent 8 }}   # your values and decrypted secrets, passed down
```

```bash
# 1. Prerequisites — CNPG roles, Keycloak realm clients, cert-manager, ingress.
#    See docs/deployment/prerequisites.md
# 2. Write your values (helm/values.example.yaml shows a participant entry) and
#    your secrets (helm/secrets.example.yaml lists every key); encrypt with sops.
# 3. Preflight the decrypted secrets — never prints a value:
sops -d overlay/staging/secrets.sops.yaml > /tmp/secrets.dec.yaml
task -d ds secrets:check FILE=/tmp/secrets.dec.yaml && rm /tmp/secrets.dec.yaml
# 4. Render, then deploy
helmfile -e staging template >/dev/null
helmfile -e staging apply
helm test -n <namespace> <release>     # each release's content checks, below
```

Three things the base does that a deployment should know:

- **Your environment name must be one ds declares** (`staging`, `production`).
  Helmfile skips a sub-helmfile in an environment it does not declare, silently
  (`no releases found`).
- **ds's base `values.yaml` lists no participants.** Helmfile merges a list over
  a list element by element, so an example list in the base would leak into
  your render. ds's own example participants are in `values.example.yaml`, read
  only by `helmfile -e example`.
- **A participant's `connector`, `edc`, `provenance` and `portal` blocks are those
  charts' values, forwarded whole.** Anything in `charts/<chart>/values.yaml` is
  settable from your values; `secrets`, `participant`, `global` and
  `existingSecret` are refused there (they come from the secrets file and the
  participant entry). The old flat spellings (`connector.governanceConfigMap`,
  `.notifyBackends`, …) fail the render naming the new key.

A `secrets.sops.yaml` beside this file is still read if present (it is
optional, and gitignored here), for an operator rendering from a ds checkout.

## Secrets

The chart never invents a secret value: templates use `required`, so a missing
value fails the render instead of deploying a default nobody chose. On top of
that, **the helmfile enforces a secret policy on the merged values** before any
release renders — the one place where every release's values are in view:

| Check | Where |
|-------|-------|
| every enabled participant has its secrets entry | every environment |
| no placeholder (`CHANGE_ME` in any spelling) or committed dev default, at any depth | every environment but `example` |
| no custody key shared: the anchor's and each participant's encryption key; two participants' encryption or EDC control keys | every environment but `example` |
| every participant's `connectorClientSecret` equal (and equal to `svcEdcSecret`): all EDCs log in as the one client `svc-edc` | every environment |
| posture A: `organisationClients.<alias>.connectorSecret` equals that participant's `organisationClientSecret` | every environment |
| no EDR signing key from the committed dev fixtures | every environment |
| `edcVault.edrSigningPublicJwk` is the private JWK without `d` (required for a provider) | every environment |
| a literal `trustAnchorDomain` equals the derived `<hosts.trustAnchor>.<baseDomain>` | every environment |

Each refusal names the key path, never the value. `task secrets:check FILE=<decrypted>.yaml`
runs the same checks plus client secrets equal to their client id (mapped from
`services/keycloak/clients*.yaml`) on the operator's machine.

Two delivery modes, switchable without template changes:

| Mode | How |
|------|-----|
| Rendered (default) | values from your secrets file → rendered `Secret` per service |
| Pre-created | set `existingSecret: <name>` per service → chart references, creates nothing |

Full key reference: [Secrets](../docs/deployment/secrets.md).

## `helm test`

Each chart that owns a surface ships a test Pod asserting **content**, not
status — the local doctor's chart-owned rows on a cluster:

| Release | Asserts |
|---------|---------|
| `ds-edc-<p>` | `https://<p>.<baseDomain>/.well-known/did.json` through the Ingress has `id` = the participant's DID |
| `ds-identity-registry-<p>` | the registry answers in-cluster and holds the participant's DID document |
| `ds-connector-<p>` (provider with governance) | `/provider/assets`, as the organisation client, is non-empty and as large as the governance's exposed set |
| `ds-portal-<p>` | through the Ingress, no session: `/join` is 200, `/` is not |

They run the ds-connector image of the same release. `tests.tlsVerify: false`
(per chart) is for a rehearsal cluster with a private CA only.

## Security posture (enforced by the charts)

- `DS_ENV=production` is hardcoded on every container — not a value, cannot be
  turned off. It flips every service's `ProductionGuard` to fail-closed.
- `DS_DEMO_IDENTITY_ENABLED` appears nowhere: an absent key cannot be set true.
- Pods run as non-root uid 10001, no privilege escalation, all capabilities
  dropped, read-only root filesystem, seccomp `RuntimeDefault`.
- Default-deny NetworkPolicies; only the ingress controller and named peers get
  through. `/metrics` reachable only from the Prometheus namespace.
- Public surface is minimal and path-scoped — see
  [Exposure and network policy](../docs/deployment/exposure.md).

## Local validation

```bash
task helm:test                       # lint, the example render, and the pilot-shaped
                                     # deployment rendered through its own helmfile
helmfile -e example template         # the whole set from the committed example
```

`task helm:test` copies `helm/` to a temporary directory (so `helm dependency
update` never writes the tree) and asserts over the parsed objects; the
pilot-shaped values are `tests/pilot/values.yaml`. See the store playbook
*rendering-and-testing-the-charts*.
