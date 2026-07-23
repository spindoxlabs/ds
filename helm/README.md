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

- **Security contract & agent guide:** [`AGENTS.md`](./AGENTS.md)
- **Design & rationale:** [`.agents/helm/plan.md`](../.agents/helm/plan.md)
- **CNPG reference manifest:** [`docs/cnpg-cluster.example.yaml`](./docs/cnpg-cluster.example.yaml)

## What deploys

| Group | Releases | Cardinality |
|-------|----------|-------------|
| authority | `ds-identity-registry` | once per dataspace |
| participant | `ds-edc`, `ds-connector`, `ds-provenance`, `ds-federated-catalog`, `ds-portal` | once per participant |

Postgres (CloudNativePG), Keycloak and cert-manager are **not** installed by
these charts — see [Prerequisites](../docs/deployment/prerequisites.md). The
dev-only `dataset-api-mock`, `caddy` and `edc-extensions` are intentionally
excluded.

> **Status:** all seven charts are implemented — `ds-common` (library),
> `ds-namespaces`, the authority `ds-identity-registry`, and the participant
> tier `ds-edc` / `ds-connector` / `ds-provenance` / `ds-federated-catalog` /
> `ds-portal`. The full `helmfile.yaml.gotmpl` composes an authority plus any
> number of participants and renders end-to-end through SOPS. Remaining work is
> hardening and CI gates — see the checklist in [`AGENTS.md`](./AGENTS.md).

## Install

```bash
# 1. Prerequisites — CNPG Cluster, Keycloak realm, cert-manager ClusterIssuer,
#    ingress controller. See docs/deployment/prerequisites.md

# 2. Configure
$EDITOR values.yaml                 # baseDomain, postgres, keycloak, participants
cp secrets.example.yaml secrets.sops.yaml
$EDITOR secrets.sops.yaml           # fill every CHANGE_ME
#   generation helpers:
#     openssl rand -hex 32
#     python -c 'import secrets;print(secrets.token_urlsafe(32))'
#     task secrets:keygen           # EC P-256 material → secrets/

# 3. Encrypt (edit .sops.yaml with your age/KMS recipient first)
sops --encrypt --in-place secrets.sops.yaml

# 4. Deploy
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
helmfile -e production diff
helmfile -e production apply
```

## Secrets

`secrets.sops.yaml` is committed **encrypted** and decrypted by helmfile at
render time. Its plaintext form must never be committed — the `.gitignore` here
blocks the usual staging names, but the responsibility is yours.

Three delivery modes, switchable without template changes:

| Mode | How |
|------|-----|
| SOPS (default) | values in `secrets.sops.yaml` → rendered `Secret` per service |
| External Secrets | `global.externalSecrets.enabled=true` → `ExternalSecret` CRs against your store |
| Pre-created | set `existingSecret: <name>` per service → chart references, creates nothing |

The chart never invents a secret value: templates use `required`, so a missing
value fails the render instead of deploying a default nobody chose. Full key
reference: [Secrets](../docs/deployment/secrets.md).

## Security posture (enforced by the charts)

- `DS_ENV=production` is hardcoded on every container — not a value, cannot be
  turned off. It flips every service's `ProductionGuard` to fail-closed.
- `DS_DEMO_IDENTITY_ENABLED` appears nowhere: an absent key cannot be set true.
- Pods run as non-root uid 10001, no privilege escalation, all capabilities
  dropped, read-only root filesystem, seccomp `RuntimeDefault`.
- Default-deny NetworkPolicies; only the ingress controller and named peers get
  through. `/metrics` reachable only from the Prometheus namespace.
- Public surface is minimal and path-scoped — see [`AGENTS.md`](./AGENTS.md)
  §Exposure and [Exposure and network policy](../docs/deployment/exposure.md).

## Local validation

```bash
helm dependency update ./charts/ds-identity-registry
helm lint ./charts/ds-identity-registry \
  --set secrets.identityRegistryEncryptionKey=x \
  --set secrets.keycloakClientSecret=y --set secrets.dbPassword=z

helmfile -e production template                                  # the real gate
helmfile -e production template | kubeconform -strict -summary   # if installed
```
