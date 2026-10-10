# A local cluster (minikube)

Run the charts on your own machine **as a deployment runs them**: `DS_ENV=production` on every
container, the secret policy armed, NetworkPolicies enforced (Calico), every host behind an
ingress with a certificate, enrolment as the operator step it is, and the `helm test` Pods and
the gates at the end. Nothing here is a development shortcut: what passes here is what a
deployment's first install will meet.

It is also how a deployment **rehearses** before its first install: it keeps its own values,
secrets and realm files, and drives the same steps with its own overrides (below).

## Needs

`minikube` (docker driver), `kubectl`, `helm`, `helmfile`, `docker`, `jq`, `openssl`, `uv`,
`task`. About 8 CPUs and 24 GB for the profile (`DS_MK_CPUS`, `DS_MK_MEMORY`). The EDC image
builds from the `ds-edc-base:0.18.0` image `task edc:base` makes.

**A kubeconfig of its own.** Every step writes or reads only `$KUBECONFIG`, refuses the
default `~/.kube/config`, and refuses any context but the profile's (`ds-minikube`) or an API
server that is not local. Your machine's default context may be a shared cluster.

## Install

```bash
export KUBECONFIG=$PWD/.minikube.kubeconfig        # any file of its own
task helm:minikube:build-images                    # once, and after a change to a service
task helm:minikube:all                             # about 15 minutes; prints each step's time
task helm:minikube:test                            # helm test, every release
task helm:minikube:gates -- all                    # every gate, each with its red case
```

`all` runs, in order (each is also `task helm:minikube:<step>`):

| Step | What |
|---|---|
| `cluster` | `minikube start -p ds-minikube --cni=calico`, the ingress and ingress-dns addons |
| `certs` | a local CA in `helm/minikube/.certs/` (gitignored), created once and then reused: the images trust it |
| `coredns` | in-cluster, `*.test` resolves to the node through ingress-dns |
| `secrets` | `helm/minikube/secrets.yaml` (gitignored) from `helm/tools/generate_secrets.py`: every key, real key material, nothing shared that must not be |
| `platform` | the bundled platform: cert-manager, CloudNativePG with one cluster (`ds-platform/ds-pg`), Keycloak in development mode with ds's dev realm `dataspaces` at `https://keycloak.ds.test`, and the CA ClusterIssuer `ds-minikube-ca` |
| `images` | the ds images into the node, each with one layer trusting the local CA (`helm/minikube/images/`); oauth2-proxy likewise, under its upstream reference |
| `databases` | one database and one owner role per service |
| `realm` | the ds clients into the bundled realm with the generated secrets: ds's client files plus the environment's organisation and collector clients (`helm/minikube/binding/keycloak/`) |
| `namespaces`, `configmaps`, `apply` | `helmfile -e minikube`: the namespaces first (the anchor's seed and the governance ConfigMaps need them), then every release |
| `enrol <p>` | per participant: mint a code at the anchor, spend it in the participant's registry pod ([Operations](operations.md#enrolment-an-operator-step)) |
| `collectors` | restart the anchor: its `bootstrap.sh` adds the holder/collector pair, which it can only do once both are enrolled |
| `data-plane` | the data-plane stand-in (ds's `dataset-api-mock`, never charted) in `ds-platform`, which the connectors' `ingressFrom` admits |

The environment (`helm/minikube/values.yaml.gotmpl`): the anchor, `example-rec` (`both`, the
consent collector, portal on) and `example-dso` (provider and holder), namespaces
`ds-authority`, `ds-example-rec`, `ds-example-dso`, base domain `ds.test`, the bundled realm and
Postgres, and the did:web internal allowance for `.ds.test` at the node's address: in-cluster,
the participants' hosts resolve to the node, a private address
([Exposure](exposure.md#when-the-cluster-resolves-the-dataspaces-own-hosts-privately)).

The bundled realm is **ds's dev realm** (users whose passwords are their usernames). It exists
for this local cluster only; the services' production guards do not depend on it.

## The gates

`task helm:minikube:gates -- <gate>...` (or `all`). Each prints `PASS`/`FAIL` with its
evidence, runs its red case, and puts back what it changed.

| Gate | Passes when | Red case (must fail, then be restored) |
|---|---|---|
| `helm-test` | every release's test Pod passes | — (see `t4.1`) |
| `t2.3` | `org apply` onboards exactly the owners the governance exposes; `owner import` first changes nothing | a governance file exposing nothing is a refusal |
| `t2.4` | the collector pair from `bootstrap.sh` is active | revoked + empty `bootstrap.sh` + restart: not active |
| `t4.1` | — | each test Pod fails: DID document of the wrong DID, `/join` behind the wall, catalogue ≠ governance, registry at zero |
| `t5.1` | every pod Ready, every publishing Job complete | (the guards: `pod-negatives`) |
| `t5.2` | `/internal/edr-jwks` from the data plane's namespace: `kid` = the signer alias, the configured public half, no private member | vault file unset: 503 |
| `t5.3` | a consumer transfer yields an EDR, the stand-in verifies it and gets `allow` from `/internal/dataplane/authorize` | no `ingressFrom` policy: the PEP calls time out |
| `t5.5` | a governance change with its checksum rolls the connector, re-runs the publishing hook, and the catalogue follows (and shrinks back on revert) | the ConfigMap changed without the checksum: nothing rolls |
| `allowance` | with the ADR-0029 allowance, enrolment is issued | refused without it, and with the suffix but an address outside the listed `/32` |
| `render-negatives` | the secret policy (render) and the preflight refuse: a placeholder, mismatched EDR halves, a shared custody key, `svc-edc` differing, a client secret equal to its id, a committed fixture key | — |
| `pod-negatives` | every guard refuses its placeholder by name on the cluster (connector, provenance, both registry kinds, portal, EDC configuration and vault seed, a dev vault); a rollout refused by its guard leaves the serving pod's STS working | — |
| `rotation` | `edcCallbackKey` rotated in one apply rolls the EDC and the connector, and a transfer afterwards still delivers its EDR | — |

One gap is printed as `GAP`, not hidden: the upstream oauth2-proxy boots on a placeholder client
secret; only the render policy and the preflight stop it.

## From a deployment's repository: rehearsing

A deployment drives the same steps with its own files, by environment variables (all in
`helm/minikube/minikube.sh`'s header):

| Variable | The deployment's |
|---|---|
| `DS_MK_HELMFILE_DIR`, `DS_MK_HELMFILE_ENV` | its own helmfile (ds's as the base) and environment |
| `DS_MK_VALUES`, `DS_MK_SECRETS` | its values and its (generated, never committed) secrets file |
| `DS_MK_BINDING` | its `seed/`, `governance/<participant>/`, `keycloak/` |
| `DS_MK_PLATFORM=external` | its own Postgres, realm and cert-manager (on the same minikube); then `DS_MK_PG_EXEC` (how to reach `psql` as a superuser), `DS_MK_TOKEN_URL`, `DS_MK_CA_DIR`, `DS_MK_ISSUER` |
| `DS_MK_DOMAIN`, `DS_MK_PROFILE`, `DS_MK_AUTHORITY_NS`, `DS_MK_PREFIX`, `DS_MK_DATA_PLANE_NS` | its names |
| `DS_MK_PARTICIPANTS`, `DS_MK_CONSUMER`, `DS_MK_PROVIDER`, `DS_MK_COLLECTORS` | its participants and the gates' roles |

With an external realm the `realm` step does not run: the realm's owner syncs the ds clients
with its own procedure (`realm-env` prints the secrets for it, to a pipe), and its file set must
be complete ([Keycloak](keycloak.md)). The seed and governance ConfigMaps are always named
`ds-seed`, `ds-governance` and `<participant>-governance`.

## Remove

```bash
task helm:minikube:destroy      # the ds releases; the platform, the databases and the CA stay
task helm:minikube:delete       # the whole profile
```

## Traps

- **Bridge CNI enforces no NetworkPolicy.** The profile is started with `--cni=calico`; on another
  CNI every `ingressFrom` and default-deny check passes vacuously.
- **`minikube image load --overwrite` keeps the old image** while a container uses it. The
  images step loads into the node's docker (`docker save | docker load` against
  `minikube docker-env`).
- **The registries' did:web resolver reads certifi's bundle only** (`trust_env=False`, on
  purpose), so the CA layer appends to it as well as to the system bundle.
- **`bootstrap.sh`'s collector step defers until both organisations are enrolled**, and re-adds a
  revoked pair on every anchor restart: a revocation must also leave `bootstrap.sh`.
- **An enrolment token admits `consumer` only by default**; the enrol step passes the roles the
  owners file declares.
- **The data plane caches the EDR verification key per process**: after an EDR key change,
  restart it.
