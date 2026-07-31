# Prerequisites

These charts deploy the dataspace application only. Four things must exist in the cluster
first, and none of them is installed here by design: they are stateful, long-lived, and usually
owned by a platform team rather than by an application release.

| Prerequisite | Why it is not in the chart |
|---|---|
| **CloudNativePG** and a `Cluster` | Backup, PITR, failover and major-version upgrades are the operator's job. A chart-owned StatefulSet would silently own data it cannot protect |
| **Keycloak** | Already operated externally. These charts consume its issuer and clients |
| **cert-manager** and a `ClusterIssuer` | The charts reference an issuer, or a pre-created secret |
| **An ingress controller** (nginx assumed) | Cluster-wide singleton |

Optional: the Prometheus Operator (for `ServiceMonitor`), the External Secrets Operator (for
`ExternalSecret` delivery).

---

## 1. PostgreSQL via CloudNativePG

Install the operator, then apply a `Cluster`. A worked example is in
[`helm/docs/cnpg-cluster.example.yaml`](https://github.com/spindoxlabs/ds/blob/main/helm/docs/cnpg-cluster.example.yaml).

```bash
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.25/releases/cnpg-1.25.0.yaml
kubectl create namespace database
kubectl apply -f helm/docs/cnpg-cluster.example.yaml
```

### One database and one role per service

Development runs every database under a single Postgres superuser. Production must not.
`.env.example` already carries a separate URL per service precisely so this split costs no code
change.

| Database | Owner role | Used by |
|---|---|---|
| `identity_registry` | `identity_registry` | ds-identity-registry |
| `connector_<participant>` | `connector_<participant>` | ds-connector |
| `provenance_<participant>` | `provenance_<participant>` | ds-provenance |
| `edc_<participant>` | `edc_<participant>` | ds-edc |

One authority database plus **three per participant** — seven for the two-participant example
shipped in `helm/values.yaml`. Each role owns its own database and has no rights on any other.
CNPG's `spec.managed.roles` and `spec.bootstrap.initdb.postInitApplicationSQL` handle this
declaratively; see the example manifest.

**The EDC needs DDL rights on its own database at first boot.** It creates its schema itself
from resources inside its JAR, and **Flyway is not on its classpath**, so "run migrations
out-of-band" means applying those `*-schema.sql` resources yourself. The least-privilege role
above is what removes the actual risk — DDL as a cluster superuser — while keeping the connector
self-migrating. Set `sqlSchemaAutocreate: false` on the `ds-edc` chart if you want the stricter
posture and are prepared to apply the DDL as a gated step.

Set the coordinates in `helm/values.yaml`:

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

The charts never install Keycloak. They need an existing realm satisfying the contract in
[Keycloak requirements](keycloak.md).

```yaml
global:
  keycloak:
    realm: dataspaces
    issuerUrl: https://sso.example.org/realms/dataspaces
    adminUrl: https://sso.example.org
    tokenUrl: https://sso.example.org/realms/dataspaces/protocol/openid-connect/token
```

`issuerUrl` is what makes every service verify a JWT's signature, audience and issuer via JWKS.
It is not optional: under `DS_ENV=production` every service refuses to start without it.

`tokenUrl` is likewise not optional — `ds-edc` declares it required and its render fails
without it.

---

## 3. cert-manager

```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace --set crds.enabled=true
```

Then either let the charts request certificates through a `ClusterIssuer`:

```yaml
global: {ingress: {tls: {clusterIssuer: letsencrypt-prod}}}
```

or supply a pre-created certificate secret, which suppresses the issuer annotation entirely:

```yaml
global: {ingress: {tls: {secretName: ds-wildcard-tls}}}
```

### DNS

Every public host is a subdomain of `global.baseDomain`, and all of them must resolve to the
ingress controller:

| Host | Purpose |
|---|---|
| `portal.<baseDomain>` | the only human-facing host — the portal **and** `/oauth2/*` |
| `<participant>.<baseDomain>` | `did:web` identity + DSP protocol + data plane, one per participant |
| `trust-anchor.<baseDomain>` | the trust-anchor DID document and the revocation list |
| `users.<baseDomain>` | user DID resolution — only when `exposeUserDids` is on |

A wildcard `*.<baseDomain>` record and a wildcard certificate cover all of them and keep adding
a participant a values-only change.

!!! danger "`did:web` must resolve over HTTPS"
    The dev stack's plaintext `:80` rewrite does not carry over, and `edc.iam.did.web.use.https`
    is `true` here. DID documents carry the public keys every trust decision rests on, so
    fetching them over plaintext would put participant identity verification in an on-path
    attacker's hands.

---

## 4. Ingress controller

nginx is assumed (`global.ingress.className: nginx`). The charts use
`nginx.ingress.kubernetes.io/rewrite-target` for `did:web` path rewriting, `use-regex` on the
user-DID rule, and the `auth-url` / `auth-signin` / `auth-response-headers` annotations on the
portal.

Those annotations are the pieces to port to a different controller — and
**`auth-response-headers` is part of the authentication boundary**, not a hardening extra, so
port it before deploying the portal, not after. See [oauth2-proxy](../services/oauth2-proxy.md).

The NetworkPolicies admit ingress from exactly one namespace:

```yaml
global:
  ingress:
    controllerNamespace: ingress-nginx
```

## Preflight checklist

```bash
kubectl get clusters.postgresql.cnpg.io -A          # CNPG cluster healthy
kubectl get clusterissuer                           # cert-manager issuer Ready
kubectl get ingressclass                            # nginx present
curl -sf $ISSUER/.well-known/openid-configuration   # Keycloak realm reachable
dig +short portal.$BASE_DOMAIN                      # DNS resolves to the load balancer
helmfile -e production template >/dev/null          # every required secret is wired
```

The last line is the intended gate: the Secret templates use `required`, so a render that
succeeds proves every mandatory secret has a value, and a render that fails names the missing
key.

Next: [Keycloak requirements](keycloak.md) → [Configuration reference](configuration.md).
