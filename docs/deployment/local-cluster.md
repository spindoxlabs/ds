# A local cluster (minikube)

Run the charts on your own machine **as a deployment runs them**: `DS_ENV=production` on every
container, the secret policy armed, NetworkPolicies enforced (Calico), every host behind an
ingress with a certificate, the seed, governance, enrolment and collector pair through the
charts, and the `helm test` Pods and the gates at the end. Nothing here is a development shortcut: what passes here is what a
deployment's first install will meet.

Two scripts, both under `helm/minikube/`, configured by `env.sh` (`DS_MK_*`):

- **`minikube.sh`, the cluster**: the minikube profile, a local CA, in-cluster DNS for the
  dataspace's hosts, and the ds images. Nothing of ds is installed by it.
- **`standalone.sh`, ds without a host platform**: stand-ins for what a deployment's own
  infrastructure provides (cert-manager, Postgres with the ds databases, a realm, a data
  plane), the generated secrets, and the releases.

**What the releases are made of is values**, `helm/minikube/values.yaml.gotmpl`: the
participants as profiles, the anchor's seed and governance and each participant's governance
(read from `helm/minikube/binding/`), enrolment on, the collector pair. There is no ConfigMap,
enrolment or anchor-restart step.

It is also how a deployment **rehearses** before its first install: it runs `minikube.sh` for
the cluster, its own infrastructure for the platform, and its own helmfile (ds's as the base)
with its own values and secrets (below).

## Needs

`minikube` (docker driver), `kubectl`, `helm`, `helmfile`, `docker`, `jq`, `openssl`, `uv`,
`task`. About 8 CPUs and 24 GB for the profile (`DS_MK_CPUS`, `DS_MK_MEMORY`). The EDC image
builds from the `ds-edc-base:0.18.0` image `task edc:base` makes.

**A kubeconfig of its own.** Every step writes or reads only `$KUBECONFIG`, which defaults to
`helm/minikube/.minikube.kubeconfig` (gitignored) when unset, refuses the default
`~/.kube/config`, and refuses any context but the profile's (`ds-minikube`) or an API
server that is not local. Your machine's default context may be a shared cluster.

## Install

```bash
# KUBECONFIG: helm/minikube/.minikube.kubeconfig unless you set another file of its own
task helm:minikube:certs                           # once: the CA the images trust
task helm:minikube:build-images                    # once, and after a change to a service
task helm:standalone:all                           # about 15 minutes; prints each step's time
task helm:standalone:test                          # helm test, every release
task helm:standalone:gates -- all                  # every gate, each with its red case
```

The cluster, `task helm:minikube:<step>` (`minikube.sh all` runs the first, second, third and
fifth):

| Step | What |
|---|---|
| `cluster` | `minikube start -p ds-minikube --cni=calico`, the ingress and ingress-dns addons |
| `certs` | a local CA in `helm/minikube/.certs/` (gitignored), created once and then reused: the images trust it |
| `coredns` | in-cluster, `*.test` resolves to the node through ingress-dns |
| `issuer` | the CA ClusterIssuer `ds-minikube-ca` over that CA (needs cert-manager) |
| `images` | the ds images into the node, each with one layer trusting the local CA (`helm/minikube/images/`); oauth2-proxy likewise, under its upstream reference |
| `build-images [svc…]` | build them from this checkout (no cluster needed) |
| `delete` | the whole profile |

ds on it without a host platform, `task helm:standalone:<step>` (`all` runs `minikube.sh all`,
then these in order up to `data-plane`):

| Step | What |
|---|---|
| `secrets` | `helm/minikube/secrets.yaml` (gitignored) from `helm/tools/generate_secrets.py` over the values: every key, real key material, nothing shared that must not be, an enrolment code per participant with enrolment on and a collector secret per collector |
| `platform` | the stand-in platform: cert-manager, CloudNativePG with one cluster (`ds-platform/ds-pg`), Keycloak in development mode with ds's dev realm `dataspaces` at `https://keycloak.ds.test`, and the issuer |
| `databases` | one database and one owner role per service |
| `realm` | the ds clients into the bundled realm with the generated secrets: ds's client files plus the environment's organisation and collector clients (`helm/minikube/binding/keycloak/`) |
| `apply` | `helmfile -e minikube apply`: the namespaces, the anchor (its seed and governance ConfigMaps rendered from the binding, its enrolment hook registering both codes, its collector Job waiting for the pair), then each participant (its governance ConfigMap, its enrolment Job spending its code once its DID document resolves) |
| `data-plane` | the data-plane stand-in (ds's `dataset-api-mock`, never charted) in `ds-platform`, which the connectors' `ingressFrom` admits |
| `test`, `gates`, `destroy` | `helm test` of every release; the gates; `helmfile destroy` |

The environment (`helm/minikube/values.yaml.gotmpl`): the anchor, `example-rec` (`both`, the
consent collector for `example-dso`, portal on, enrolment on) and `example-dso` (provider and
holder, enrolment on), namespaces
`ds-authority`, `ds-example-rec`, `ds-example-dso`, base domain `ds.test`, the bundled realm and
Postgres, and the did:web internal allowance for `.ds.test` at the node's address: in-cluster,
the participants' hosts resolve to the node, a private address
([Exposure](exposure.md#when-the-cluster-resolves-the-dataspaces-own-hosts-privately)).

The bundled realm is **ds's dev realm** (users whose passwords are their usernames). It exists
for this local cluster only; the services' production guards do not depend on it.

## The gates

`task helm:standalone:gates -- <gate>...` (or `all`; `helm/minikube/gates.sh` directly is the
same). Each prints `PASS`/`FAIL` with its
evidence, runs its red case, and puts back what it changed.

| Gate | Passes when | Red case (must fail, then be restored) |
|---|---|---|
| `helm-test` | every release's test Pod passes | — (see `t4.1`) |
| `t2.3` | `org apply` onboards exactly the owners the governance exposes; `owner import` first changes nothing | a governance file exposing nothing is a refusal |
| `t2.4` | the collector pair from the anchor's collector Job is active; after `collector revoke` and a re-run of the Job (it adds the pair again) it is still revoked, and the Job's log says by whom, when and why; `collector reinstate` makes it active | the re-run is the red case: before the fix it re-activated the pair |
| `t4.1` | — | each test Pod fails: DID document of the wrong DID, `/join` behind the wall, catalogue ≠ governance, registry at zero |
| `t5.1` | every pod Ready, every publishing Job complete | (the guards: `pod-negatives`) |
| `t5.2` | `/internal/edr-jwks` from the data plane's namespace: `kid` = the signer alias, the configured public half, no private member | vault file unset: 503 |
| `t5.3` | a consumer transfer yields an EDR, the stand-in verifies it and gets `allow` from `/internal/dataplane/authorize` | no `ingressFrom` policy: the PEP calls time out |
| `consumer-list` | the consumer's organisation lists its own requests with a token asked for `management-api:negotiations:read` only; a repeated negotiation answers 409 naming a listed `request_id` | a token with no negotiation scope: 403; the read-only token negotiating: 403 |
| `t5.5` | a change to the governance file the values read rolls the connector (the checksum follows the content), re-runs the publishing hook, and the catalogue follows (and shrinks back on revert) | the chart's ConfigMap edited out of band, the values unchanged: nothing rolls |
| `allowance` | with the ADR-0029 allowance, enrolment is issued | refused without it, and with the suffix but an address outside the listed `/32` |
| `allowance-services` | the connector, provenance and the EDC log their ADR-0029 allowance at start; in the connector and provenance pods `ds_auth.did_web` resolves the trust anchor with the allowance | the same fetch without it: refused (`non-public address`); the provider EDC without it: the consumer's flow is refused and the EDC logs the refusal, then restored |
| `render-negatives` | the secret policy (render) and the preflight refuse: a placeholder, mismatched EDR halves, a shared custody key, `svc-edc` differing, a client secret equal to its id, a committed fixture key | — |
| `pod-negatives` | every guard refuses its placeholder by name on the cluster (connector, provenance, both registry kinds, portal, EDC configuration and vault seed, a dev vault); a rollout refused by its guard leaves the serving pod's STS working | — |
| `rotation` | `edcCallbackKey` rotated in one apply rolls the EDC and the connector, and a transfer afterwards still delivers its EDR | — |

One gap is printed as `GAP`, not hidden: the upstream oauth2-proxy boots on a placeholder client
secret; only the render policy and the preflight stop it.

## From a deployment's repository: rehearsing

A deployment with its own infrastructure (on the same minikube) uses **`minikube.sh` only**,
for the cluster, the CA, CoreDNS and the images, and none of `standalone.sh`'s stand-ins: its
infrastructure creates the databases and the realm clients, and its own helmfile (ds's as the
base) carries the participants, the seed and governance content, enrolment and the collector
pairs as values. `minikube.sh`'s variables (`env.sh`):

| Variable | The deployment's |
|---|---|
| `DS_MK_PROFILE`, `DS_MK_DOMAIN` | its profile and its base domain (under `.test`) |
| `DS_MK_CA_DIR`, `DS_MK_ISSUER` | its CA (one for both stacks) and the ClusterIssuer name |
| `DS_MK_IMAGE_TAG` | the tag the images are built and loaded under (its values set the same) |
| `DS_MK_CPUS`, `DS_MK_MEMORY`, `DS_MK_K8S_VERSION` | the profile's size |

The releases are then `helmfile -e <its environment> apply` from its repository, with
`DS_MK_NODE_IP=$(minikube -p <profile> ip)` if its values read the node address. The gates
(`gates.sh`) also read `DS_MK_HELMFILE_DIR`, `DS_MK_HELMFILE_ENV`, `DS_MK_SECRETS`,
`DS_MK_BINDING`, `DS_MK_CONSUMER`, `DS_MK_PROVIDER`, `DS_MK_AUTHORITY_NS`, `DS_MK_PREFIX`,
`DS_MK_DATA_PLANE_NS` and `DS_MK_PG_EXEC`.

The realm's owner syncs the ds clients with its own procedure (`standalone.sh realm-env` prints
the secrets of a generated file, to a pipe), and its file set must be complete
([Keycloak](keycloak.md)).

## Remove

```bash
task helm:standalone:destroy    # the ds releases; the platform, the databases and the CA stay
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
- **The collector Job waits until both organisations are enrolled**, up to
  `enrolment.activeDeadlineSeconds`; a Job that ran out of time stays failed until its pairs
  (or the image) change, or until it is deleted and the release applied again. A revoked pair
  stays revoked across re-runs (`collector add` leaves it and says so); lift it with
  `ir-cli collector reinstate`.
- **An enrolment token admits `consumer` only by default** by hand; the charts derive the
  roles from the participant's role (`both` → `provider,consumer`), which the owners file must
  admit.
- **The data plane caches the EDR verification key per process**: after an EDR key change,
  restart it.
