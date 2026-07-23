# Prerequisites

These charts deploy the dataspace application only. Four things must exist in the
cluster first — none of them is installed here, by design: they are stateful,
long-lived, and usually owned by a platform team rather than by an application
release.

| Prerequisite | Why it is not in the chart |
|--------------|----------------------------|
| **CloudNativePG** + a `Cluster` | Backup, PITR, failover and major-version upgrades are the operator's job. A chart-owned StatefulSet would silently own data it cannot protect. |
| **Keycloak** | Already operated externally. These charts consume its issuer and clients; they never mutate the realm unless `global.keycloak.sync.enabled` is set. |
| **cert-manager** + a `ClusterIssuer` | The charts only reference the issuer or a pre-created secret. |
| **An ingress controller** (nginx assumed) | Cluster-wide singleton. |

Optional: Prometheus Operator (for `ServiceMonitor`), External Secrets Operator
(for `global.externalSecrets.enabled`).

---

## 1. PostgreSQL via CloudNativePG

Install the operator, then apply a `Cluster`. A worked example is in
[`cnpg-cluster.example.yaml`](./cnpg-cluster.example.yaml).

```bash
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.25/releases/cnpg-1.25.0.yaml
kubectl create namespace database
kubectl apply -f helm/docs/cnpg-cluster.example.yaml
```

### One database and one role per service

Dev uses a single Postgres superuser for all six databases. Production must not.
`.env.example` already carries a separate URL per service precisely so this split
costs no code change.

| Database | Owner role | Used by |
|----------|-----------|---------|
| `identity_registry` | `identity_registry` | ds-identity-registry |
| `connector_<participant>` | `connector_<participant>` | ds-connector |
| `provenance_<participant>` | `provenance_<participant>` | ds-provenance |
| `edc_<participant>` | `edc_<participant>` | ds-edc |

Each role owns its own database and has no rights on any other. CNPG's
`spec.managed.roles` and `spec.bootstrap.initdb.postInitApplicationSQL` handle
this declaratively — see the example manifest.

The EDC needs DDL rights on its own schema at first boot (Flyway migrates
in-process), but `edc.sql.schema.autocreate` stays `false`: migrations run as a
gated step, not as superuser DDL on every restart.

Set the resulting coordinates in `helm/values.yaml`:

```yaml
global:
  postgres:
    host: ds-pg-rw.database.svc.cluster.local
    port: 5432
    sslMode: require
```

and the per-role passwords in `secrets.sops.yaml`.

---

## 2. Keycloak

The charts never install Keycloak. They need an existing realm that satisfies the
contract in [`keycloak-requirements.md`](./keycloak-requirements.md) — service
clients with the right scopes, user groups mirroring those scope names, brute
force protection, and the three audit event flags NIS2 evidence depends on.

Point the charts at it:

```yaml
global:
  keycloak:
    realm: dataspaces
    issuerUrl: https://sso.example.org/realms/dataspaces
    adminUrl: https://sso.example.org
    tokenUrl: https://sso.example.org/realms/dataspaces/protocol/openid-connect/token
```

Setting `issuerUrl` is what makes `ds_auth` verify JWT signature, audience and
issuer via JWKS. It is not optional: with `DS_ENV=production` every service
refuses to start without it.

---

## 3. cert-manager

```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace --set crds.enabled=true
```

Then either let the charts request certificates through a `ClusterIssuer`:

```yaml
global:
  ingress:
    tls:
      clusterIssuer: letsencrypt-prod
```

or supply a pre-created certificate secret and leave the issuer unused:

```yaml
global:
  ingress:
    tls:
      secretName: ds-wildcard-tls
```

### DNS

Every public host is a subdomain of `global.baseDomain`. All of these must
resolve to the ingress controller:

| Host | Purpose |
|------|---------|
| `portal.<baseDomain>` | the only human-facing host |
| `<participant>.<baseDomain>` | did:web identity + DSP protocol + data plane, one per participant |
| `trust-anchor.<baseDomain>` | trust anchor DID document + StatusList2021 |
| `users.<baseDomain>` | user DID resolution — only if `authority.identityRegistry.exposeUserDids` |

A wildcard `*.<baseDomain>` record and a wildcard certificate cover all of them
and keep adding a participant a values-only change.

**did:web resolves over HTTPS on port 443.** The dev stack's `:80` Caddy hack
does not carry over, and `edc.iam.did.web.use.https` is `true` in these charts:
DID documents carry the public keys every trust decision rests on, so fetching
them over plaintext would put participant identity in an on-path attacker's
hands.

---

## 4. Ingress controller

nginx is assumed (`global.ingress.className: nginx`). The charts use
`nginx.ingress.kubernetes.io/rewrite-target` for did:web path rewriting. On a
different controller, that annotation and the `use-regex` rules in the
identity-registry ingress are the only controller-specific pieces to port.

If your controller does not run in `ingress-nginx`, set the namespace so the
NetworkPolicies allow it through:

```yaml
global:
  ingress:
    controllerNamespace: ingress-nginx
```

---

## Preflight checklist

```bash
kubectl get clusters.postgresql.cnpg.io -A          # CNPG cluster healthy
kubectl get clusterissuer                           # cert-manager issuer Ready
kubectl get ingressclass                            # nginx present
curl -sf $ISSUER/.well-known/openid-configuration   # Keycloak realm reachable
dig +short portal.$BASE_DOMAIN                      # DNS resolves to the LB
task secrets:check                                  # no dev defaults remain
```
