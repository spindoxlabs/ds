#!/usr/bin/env bash
# A local minikube cluster running the ds charts under DS_ENV=production, as a deployment
# would: Calico (NetworkPolicies are enforced), ingress with a local CA, the anchor and
# two participants, enrolment as an operator step, a data-plane stand-in, `helm test`
# and the gates. docs/deployment/local-cluster.md is the procedure; `task helm:minikube:*`
# runs these steps.
#
#   KUBECONFIG=<a kubeconfig of its own> helm/minikube/minikube.sh <step> [args]
#
# Steps (`all` runs them in this order and times each):
#   cluster        the minikube profile ($DS_MK_PROFILE), written into $KUBECONFIG only
#   certs          a local CA in $DS_MK_CA_DIR (created once, then reused: the images trust it)
#   coredns        `.test` names resolve, in-cluster, to the node (ingress-dns)
#   platform       bundled: cert-manager, CloudNativePG + one cluster, Keycloak with ds's
#                  dev realm (DS_MK_PLATFORM=external skips it: bring your own)
#   issuer         a CA ClusterIssuer over $DS_MK_CA_DIR for the ds hosts
#   build-images [svc...]  build the ds images from this checkout (no cluster needed)
#   images         load them into the node, each with the local-CA layer
#   secrets        generate $DS_MK_SECRETS if it does not exist
#   databases      one database and owner role per service ($DS_MK_PG_EXEC)
#   realm          sync the ds clients into the bundled realm (bundled platform only)
#   realm-env      print the realm's client secrets as env lines (pipe only)
#   namespaces     the ds-namespaces release (the ConfigMaps need the namespaces)
#   configmaps     the anchor's seed and governance, each provider's governance
#   apply          helmfile apply, every release
#   enrol <p>      mint a code at the anchor, spend it in the participant's registry
#   collectors     restart the anchor so bootstrap.sh's deferred collector step runs
#   data-plane     the data-plane stand-in in $DS_MK_DATA_PLANE_NS
#   test           helm test, every release
#   gates [gate..] the gates (helm/minikube/gates.sh)
#   destroy        helmfile destroy (the ds releases only)
#   delete         minikube delete of the profile
#
# Every step that touches the cluster refuses unless the kubectl context is
# $DS_MK_PROFILE and its API server is local.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
HELM_DIR=$(cd "$HERE/.." && pwd)
DS_SRC=$(cd "$HELM_DIR/.." && pwd)

# ── Configuration: generic defaults; a deployment overrides them ───────────────
DS_MK_PROFILE=${DS_MK_PROFILE:-ds-minikube}
DS_MK_K8S_VERSION=${DS_MK_K8S_VERSION:-v1.33.0}
DS_MK_CPUS=${DS_MK_CPUS:-8}
DS_MK_MEMORY=${DS_MK_MEMORY:-24g}
DS_MK_DOMAIN=${DS_MK_DOMAIN:-ds.test}               # under .test: CoreDNS forwards it
DS_MK_CA_DIR=${DS_MK_CA_DIR:-$HERE/.certs}           # ca.crt + ca.key
DS_MK_ISSUER=${DS_MK_ISSUER:-ds-minikube-ca}
DS_MK_PLATFORM=${DS_MK_PLATFORM:-bundled}            # bundled | external
DS_MK_PLATFORM_NS=${DS_MK_PLATFORM_NS:-ds-platform}
DS_MK_HELMFILE_DIR=${DS_MK_HELMFILE_DIR:-$HELM_DIR}  # where `helmfile` runs
DS_MK_HELMFILE_ENV=${DS_MK_HELMFILE_ENV:-minikube}
DS_MK_VALUES=${DS_MK_VALUES:-$HERE/values.yaml.gotmpl}
DS_MK_SECRETS=${DS_MK_SECRETS:-$HERE/secrets.yaml}
DS_MK_BINDING=${DS_MK_BINDING:-$HERE/binding}        # seed/, governance/<p>/, keycloak/
DS_MK_COLLECTORS=${DS_MK_COLLECTORS:-example-rec}
DS_MK_PARTICIPANTS=${DS_MK_PARTICIPANTS:-example-rec example-dso}
DS_MK_CONSUMER=${DS_MK_CONSUMER:-example-rec}        # the gates' consumer
DS_MK_PROVIDER=${DS_MK_PROVIDER:-example-dso}        # the gates' provider and holder
DS_MK_AUTHORITY_NS=${DS_MK_AUTHORITY_NS:-ds-authority}
DS_MK_PREFIX=${DS_MK_PREFIX:-ds-}
DS_MK_DATA_PLANE_NS=${DS_MK_DATA_PLANE_NS:-$DS_MK_PLATFORM_NS}
DS_MK_TOKEN_URL=${DS_MK_TOKEN_URL:-https://keycloak.$DS_MK_DOMAIN/realms/dataspaces/protocol/openid-connect/token}
DS_MK_PG_EXEC=${DS_MK_PG_EXEC:-kubectl exec -i -n $DS_MK_PLATFORM_NS ds-pg-1 -c postgres -- psql -v ON_ERROR_STOP=1 -q -U postgres}
DS_MK_IMAGE_TAG=${DS_MK_IMAGE_TAG:-minikube}
DS_MK_SYNC_IMAGE=${DS_MK_SYNC_IMAGE:-ghcr.io/celine-eu/celine-policies:v1.7.0}
DS_MK_LABEL=${DS_MK_LABEL:-ds-minikube}              # enrolment-token label
DS_IMAGES=(connector identity-registry provenance portal edc-connector dataset-api-mock)
OAUTH2_PROXY_IMAGE=quay.io/oauth2-proxy/oauth2-proxy:v7.11.0
export DS_IMAGE_TAG=$DS_MK_IMAGE_TAG
read -r -a PARTICIPANTS <<<"$DS_MK_PARTICIPANTS"

die() { echo "minikube.sh: $*" >&2; exit 1; }

kubeconfig_guard() {
  # A machine's default context may be a shared cluster: this setup writes its context
  # into a kubeconfig of its own and never touches the default one.
  [ -n "${KUBECONFIG:-}" ] || die "set KUBECONFIG to a kubeconfig of its own first"
  [ "$(readlink -f "$KUBECONFIG")" != "$(readlink -f "$HOME/.kube/config")" ] \
    || die "KUBECONFIG is the default kubeconfig: refusing"
}

guard() {
  kubeconfig_guard
  local ctx server
  ctx=$(kubectl config current-context 2>/dev/null) || die "no current kubectl context"
  [ "$ctx" = "$DS_MK_PROFILE" ] || die "kubectl context is '$ctx', not $DS_MK_PROFILE: refusing"
  server=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
  case "$server" in
    https://192.168.*|https://127.0.0.1*|https://localhost*) ;;
    *) die "API server $server is not local: refusing" ;;
  esac
}

node_ip() { minikube -p "$DS_MK_PROFILE" ip; }

# sec <python expression over d (the file) and s (its `secrets:`)>; never echoed.
sec() {
  [ -f "$DS_MK_SECRETS" ] || die "$DS_MK_SECRETS missing: run the secrets step"
  uv run -q --no-project --with pyyaml python -c "
import yaml
d = yaml.safe_load(open('$DS_MK_SECRETS'))
s = d['secrets']
print($1)"
}

hf() {
  # The values files read DS_MK_NODE_IP (the did:web internal allowance, ADR-0029).
  (cd "$DS_MK_HELMFILE_DIR" && DS_MK_NODE_IP=$(node_ip) helmfile -e "$DS_MK_HELMFILE_ENV" "$@")
}

subst() {  # fill ${NAME} placeholders of a manifest from the arguments NAME=value
  local file=$1; shift
  local text; text=$(cat "$file")
  for kv in "$@"; do text=${text//\$\{${kv%%=*}\}/${kv#*=}}; done
  printf '%s\n' "$text"
}

node_load() {
  # Into the node's docker, not `minikube image load --overwrite`, which silently keeps
  # the old image while a running container uses it.
  docker save "$1" | (eval "$(minikube -p "$DS_MK_PROFILE" docker-env)" && docker load -q)
}

# ── Steps ──────────────────────────────────────────────────────────────────────

step_cluster() {
  kubeconfig_guard
  # Calico, not the default bridge CNI: bridge enforces no NetworkPolicy, so the charts'
  # default-deny and every ingressFrom check would pass vacuously.
  minikube start -p "$DS_MK_PROFILE" --driver=docker --cpus="$DS_MK_CPUS" --memory="$DS_MK_MEMORY" \
    --disk-size=60g --kubernetes-version="$DS_MK_K8S_VERSION" --cni=calico
  minikube -p "$DS_MK_PROFILE" addons enable ingress
  minikube -p "$DS_MK_PROFILE" addons enable ingress-dns
  guard
}

step_certs() {
  if [ -f "$DS_MK_CA_DIR/ca.crt" ] && [ -f "$DS_MK_CA_DIR/ca.key" ]; then
    echo "reusing the CA in $DS_MK_CA_DIR"; return
  fi
  mkdir -p "$DS_MK_CA_DIR"
  ( umask 077
    openssl genrsa -out "$DS_MK_CA_DIR/ca.key" 4096 2>/dev/null )
  openssl req -new -x509 -sha256 -days 3650 -key "$DS_MK_CA_DIR/ca.key" -out "$DS_MK_CA_DIR/ca.crt" \
    -subj "/CN=ds-minikube-local-ca" -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" -addext "subjectKeyIdentifier=hash"
  echo "created a CA in $DS_MK_CA_DIR (trust ca.crt in a browser to open the hosts)"
}

step_coredns() {
  # In-cluster, a `.test` name resolves to the node through ingress-dns, as the host does.
  # That is a private address, which the registries' did:web resolver admits only through
  # the ADR-0029 allowance the values set (`.<domain>` + the node address as a /32).
  # Appended with jq: a JSON patch carrying the Corefile's raw newlines is refused.
  local ip corefile
  ip=$(node_ip)
  kubectl rollout status deployment/coredns -n kube-system --timeout=120s
  corefile=$(kubectl get cm coredns -n kube-system -o jsonpath='{.data.Corefile}')
  if ! grep -q '^test:53' <<<"$corefile"; then
    kubectl get cm coredns -n kube-system -o json \
      | jq --arg add "$(printf 'test:53 {\n    errors\n    forward . %s\n    cache 30\n}\n' "$ip")" \
           '.data.Corefile += $add' | kubectl apply -f -
    kubectl rollout restart deployment/coredns -n kube-system
    kubectl rollout status deployment/coredns -n kube-system --timeout=120s
  fi
}

step_issuer() {
  kubectl create secret tls "$DS_MK_ISSUER" -n cert-manager \
    --cert="$DS_MK_CA_DIR/ca.crt" --key="$DS_MK_CA_DIR/ca.key" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: $DS_MK_ISSUER
spec:
  ca:
    secretName: $DS_MK_ISSUER
EOF
  kubectl wait --for=condition=Ready "clusterissuer/$DS_MK_ISSUER" --timeout=120s
}

step_platform() {
  if [ "$DS_MK_PLATFORM" != bundled ]; then
    echo "DS_MK_PLATFORM=$DS_MK_PLATFORM: Postgres, Keycloak and cert-manager are the deployment's"; return
  fi
  helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
  helm repo add cnpg https://cloudnative-pg.github.io/charts >/dev/null 2>&1 || true
  helm repo update jetstack cnpg >/dev/null
  helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
    --version v1.16.3 --set crds.enabled=true --wait --timeout 600s
  helm upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace \
    --version 0.26.0 --wait --timeout 600s
  step_issuer
  kubectl create namespace "$DS_MK_PLATFORM_NS" --dry-run=client -o yaml | kubectl apply -f -
  # the CNPG webhook answers a few seconds after its Deployment is ready
  for _ in $(seq 1 30); do
    subst "$HERE/platform/postgres.yaml" NAMESPACE="$DS_MK_PLATFORM_NS" | kubectl apply -f - 2>/dev/null && break
    sleep 5
  done
  kubectl create secret generic keycloak-admin -n "$DS_MK_PLATFORM_NS" \
    --from-literal=username=admin --from-literal=password="$(sec "d['realmOnly']['keycloakAdminPassword']")" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl create configmap keycloak-realm -n "$DS_MK_PLATFORM_NS" \
    --from-file=realm-dataspaces-dev.json="$DS_SRC/services/keycloak/realm-dataspaces-dev.json" \
    --dry-run=client -o yaml | kubectl apply -f -
  subst "$HERE/platform/keycloak.yaml" NAMESPACE="$DS_MK_PLATFORM_NS" DOMAIN="$DS_MK_DOMAIN" ISSUER="$DS_MK_ISSUER" \
    | kubectl apply -f -
  kubectl wait --for=condition=Ready "cluster.postgresql.cnpg.io/ds-pg" -n "$DS_MK_PLATFORM_NS" --timeout=600s
  kubectl rollout status deploy/keycloak -n "$DS_MK_PLATFORM_NS" --timeout=600s
}

step_build_images() {
  # Each local image is the plain build plus one layer that trusts the local CA
  # (images/Dockerfile.local-ca). Needs no cluster.
  local ctx svc plain img user build=("$@")
  [ ${#build[@]} -gt 0 ] || build=("${DS_IMAGES[@]}")
  ctx=$(mktemp -d); cp "$DS_MK_CA_DIR/ca.crt" "$ctx/ca.crt"
  for svc in "${build[@]}"; do
    plain=ghcr.io/spindoxlabs/ds-$svc:$DS_MK_IMAGE_TAG-plain
    img=ghcr.io/spindoxlabs/ds-$svc:$DS_MK_IMAGE_TAG
    echo "== build $plain"
    if [ "$svc" = edc-connector ]; then
      # The base exists only where `task edc:base` ran (services/edc-connector).
      docker build -q -t "$plain" -f "$DS_SRC/services/edc-connector/Dockerfile" \
        --build-arg EDC_BASE_IMAGE=ds-edc-base:0.18.0 "$DS_SRC"
    else
      docker build -q -t "$plain" -f "$DS_SRC/services/$svc/Dockerfile" "$DS_SRC"
    fi
    user=$(docker inspect -f '{{.Config.User}}' "$plain")
    docker build -q -t "$img" -f "$HERE/images/Dockerfile.local-ca" \
      --build-arg BASE="$plain" --build-arg RUNTIME_USER="$user" "$ctx"
  done
  rm -rf "$ctx"
}

step_images() {
  # The ds images, and oauth2-proxy (upstream; its chart sets no image or env) as a
  # node-only copy with the same CA under its upstream reference.
  local svc ctx
  for svc in "${DS_IMAGES[@]}"; do
    docker image inspect "ghcr.io/spindoxlabs/ds-$svc:$DS_MK_IMAGE_TAG" >/dev/null 2>&1 \
      || die "ghcr.io/spindoxlabs/ds-$svc:$DS_MK_IMAGE_TAG not built: run build-images"
    echo "== load ghcr.io/spindoxlabs/ds-$svc:$DS_MK_IMAGE_TAG"
    node_load "ghcr.io/spindoxlabs/ds-$svc:$DS_MK_IMAGE_TAG"
  done
  ctx=$(mktemp -d); cp "$DS_MK_CA_DIR/ca.crt" "$ctx/ca.crt"
  docker image inspect "$OAUTH2_PROXY_IMAGE" >/dev/null 2>&1 || docker pull -q "$OAUTH2_PROXY_IMAGE"
  docker build -q -t ds-minikube/oauth2-proxy:local-ca -f "$HERE/images/Dockerfile.local-ca-distroless" \
    --build-arg BASE="$OAUTH2_PROXY_IMAGE" "$ctx"
  rm -rf "$ctx"
  node_load ds-minikube/oauth2-proxy:local-ca
  (eval "$(minikube -p "$DS_MK_PROFILE" docker-env)" && docker tag ds-minikube/oauth2-proxy:local-ca "$OAUTH2_PROXY_IMAGE")
}

step_secrets() {
  local args=(--values "$DS_MK_VALUES" --out "$DS_MK_SECRETS")
  for c in $DS_MK_COLLECTORS; do args+=(--collector "$c"); done
  uv run -q --no-project --with pyyaml --with cryptography python "$HELM_DIR/tools/generate_secrets.py" "${args[@]}"
}

step_databases() {
  # One database and one owner role of the same name per service (docs/deployment/
  # operations.md, "Adding a participant"). Passwords on stdin, never on a command line.
  local db pw
  for db in $(sec "'\n'.join(s['postgres'])"); do
    pw=$(sec "s['postgres']['$db']")
    $DS_MK_PG_EXEC <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$db') THEN CREATE ROLE "$db" LOGIN; END IF;
END \$\$;
ALTER ROLE "$db" WITH LOGIN PASSWORD '$pw';
SQL
    $DS_MK_PG_EXEC -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 \
      || $DS_MK_PG_EXEC -c "CREATE DATABASE \"$db\" OWNER \"$db\""
    echo "  database $db: ready"
  done
}

step_realm_env() {
  # The realm's client secrets as env lines, from the secrets file: ds's service clients,
  # one organisation client per participant, one collector client per collector.
  sec "'\n'.join([
    'SVC_DS_IDENTITY_REGISTRY_SECRET=' + s['svcDsIdentityRegistrySecret'],
    'SVC_DS_ONBOARDING_SECRET=' + s['svcDsOnboardingSecret'],
    'SVC_DS_PORTAL_SECRET=' + s['svcDsPortalSecret'],
    'SVC_DS_CONNECTOR_SECRET=' + s['svcDsConnectorSecret'],
    'SVC_DS_FEDERATED_CATALOG_SECRET=' + s['svcDsFederatedCatalogSecret'],
    'SVC_DS_DATASET_API_SECRET=' + s['svcDsDatasetApiSecret'],
    'SVC_EDC_SECRET=' + s['svcEdcSecret'],
    'SVC_DS_PUBLISHER_SECRET=' + d['realmOnly']['publisherSecret'],
    'SVC_DS_PROVENANCE_SECRET=' + d['realmOnly']['provenanceSecret'],
  ] + [
    'SVC_DS_CONNECTOR_%s_SECRET=%s' % (p.upper().replace('-', '_'), v['organisationClientSecret'])
    for p, v in s['participants'].items()
  ] + [
    'SVC_DS_COLLECTOR_%s_SECRET=%s' % (a.upper().replace('-', '_'), v['collectorSecret'])
    for a, v in d['realmOnly']['collectorClients'].items()
  ])"
}

step_realm() {
  [ "$DS_MK_PLATFORM" = bundled ] || die "the realm step syncs the bundled realm; an external realm is synced by its owner"
  local env; env=$(mktemp)
  { step_realm_env; echo; echo "KEYCLOAK_ADMIN_USERNAME=admin"
    echo "KEYCLOAK_ADMIN_PASSWORD=$(sec "d['realmOnly']['keycloakAdminPassword']")"; } > "$env"
  kubectl create secret generic keycloak-sync-env -n "$DS_MK_PLATFORM_NS" --from-env-file="$env" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  rm -f "$env"
  kubectl create configmap keycloak-clients -n "$DS_MK_PLATFORM_NS" \
    --from-file=clients.dataspaces.yaml="$DS_SRC/services/keycloak/clients.dataspaces.yaml" \
    --from-file=clients.yaml="$DS_SRC/services/keycloak/clients.yaml" \
    --from-file=clients.energy.yaml="$DS_SRC/services/keycloak/clients.energy.yaml" \
    --from-file=clients.organisations.yaml="$DS_MK_BINDING/keycloak/clients.organisations.yaml" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl delete job keycloak-sync -n "$DS_MK_PLATFORM_NS" --ignore-not-found >/dev/null
  subst "$HERE/platform/realm-sync.yaml" NAMESPACE="$DS_MK_PLATFORM_NS" SYNC_IMAGE="$DS_MK_SYNC_IMAGE" | kubectl apply -f -
  kubectl wait --for=condition=Complete job/keycloak-sync -n "$DS_MK_PLATFORM_NS" --timeout=600s \
    || { kubectl logs -n "$DS_MK_PLATFORM_NS" job/keycloak-sync --tail=40; die "realm sync failed"; }
  kubectl logs -n "$DS_MK_PLATFORM_NS" job/keycloak-sync --tail=8
}

step_namespaces() { hf -l name=ds-namespaces apply --suppress-diff; }

configmap_from() {
  local ns=$1 name=$2; shift 2
  kubectl create configmap "$name" -n "$ns" "$@" --dry-run=client -o yaml | kubectl apply -f -
}

step_configmaps() {
  # The anchor's seed (`ds-seed`) and governance (`ds-governance`), and `<p>-governance`
  # per provider: the names the values files point at.
  local b=$DS_MK_BINDING args=() p
  configmap_from "$DS_MK_AUTHORITY_NS" ds-seed \
    --from-file=agreements.yaml="$b/seed/agreements.yaml" \
    --from-file=participation-en.md="$b/seed/content/participation-en.md" \
    --from-file=owners.yaml="$b/seed/owners.yaml" \
    --from-file=bootstrap.sh="$b/seed/bootstrap.sh"
  for p in "${PARTICIPANTS[@]}"; do
    [ -f "$b/governance/$p/governance.yaml" ] || continue
    args+=(--from-file="$p.governance.yaml=$b/governance/$p/governance.yaml")
    configmap_from "$DS_MK_PREFIX$p" "$p-governance" --from-file=governance.yaml="$b/governance/$p/governance.yaml"
  done
  configmap_from "$DS_MK_AUTHORITY_NS" ds-governance "${args[@]}"
}

step_apply() { hf apply --suppress-diff "$@"; }

step_enrol() {
  # The operator step (docs/deployment/operations.md, "Enrolment"): the token admits the
  # roles the owners file declares (its default is `consumer` only), with the dataspace
  # query scope, and a consumer's own membership scope.
  local p=${1:?participant name} roles scopes code
  roles=$(uv run -q --no-project --with pyyaml python -c "
import yaml
o = next(x for x in yaml.safe_load(open('$DS_MK_BINDING/seed/owners.yaml'))['owners'] if x['id'] == '$p')
print(','.join(o['dataspace']['roles']))")
  scopes="--scope dataspaces.query"
  [[ ",$roles," == *",consumer,"* ]] && scopes+=" --scope owner:$p:member"
  if kubectl exec -n "$DS_MK_PREFIX$p" "deploy/ds-identity-registry-$p" -c identity-registry -- \
       ir-cli participant status --quiet >/dev/null 2>&1; then
    echo "  $p: already enrolled"; return 0
  fi
  # shellcheck disable=SC2086
  code=$(kubectl exec -n "$DS_MK_AUTHORITY_NS" deploy/ds-identity-registry -c identity-registry -- \
           ir-cli org enrolment-token --alias "$p" --roles "$roles" $scopes --label "$DS_MK_LABEL")
  [ -n "$code" ] || die "no enrolment code minted for $p"
  # The code goes from one pod to the other on stdin and is never printed.
  printf '%s\n' "$code" | kubectl exec -i -n "$DS_MK_PREFIX$p" "deploy/ds-identity-registry-$p" \
    -c identity-registry -- sh -c 'read -r CODE; ir-cli participant init --code "$CODE"'
}

step_collectors() {
  kubectl rollout restart -n "$DS_MK_AUTHORITY_NS" deploy/ds-identity-registry
  kubectl rollout status -n "$DS_MK_AUTHORITY_NS" deploy/ds-identity-registry --timeout=300s
  kubectl exec -n "$DS_MK_AUTHORITY_NS" deploy/ds-identity-registry -c identity-registry -- ir-cli collector list
}

step_data_plane() {
  kubectl create secret generic ds-data-plane -n "$DS_MK_DATA_PLANE_NS" \
    --from-literal=serviceClientSecret="$(sec "s['svcDsDatasetApiSecret']")" \
    --dry-run=client -o yaml | kubectl apply -f -
  subst "$HERE/data-plane.yaml" NAMESPACE="$DS_MK_DATA_PLANE_NS" \
    IMAGE="ghcr.io/spindoxlabs/ds-dataset-api-mock:$DS_MK_IMAGE_TAG" TOKEN_URL="$DS_MK_TOKEN_URL" \
    CONNECTOR_URL="http://ds-connector-$DS_MK_PROVIDER.$DS_MK_PREFIX$DS_MK_PROVIDER.svc.cluster.local:30001" \
    | kubectl apply -f -
  kubectl rollout status -n "$DS_MK_DATA_PLANE_NS" deploy/ds-data-plane --timeout=180s
}

step_test() {
  local rc=0 r
  for r in $(hf list --output json 2>/dev/null | jq -r '.[] | select(.name != "ds-namespaces") | "\(.namespace)/\(.name)"'); do
    echo "== helm test ${r#*/}"
    helm test -n "${r%/*}" "${r#*/}" --logs || rc=1
  done
  return $rc
}

step_gates() {
  export DS_MK_PROFILE DS_MK_DOMAIN DS_MK_HELMFILE_DIR DS_MK_HELMFILE_ENV DS_MK_SECRETS DS_MK_BINDING \
    DS_MK_CONSUMER DS_MK_PROVIDER DS_MK_AUTHORITY_NS DS_MK_PREFIX DS_MK_DATA_PLANE_NS DS_MK_PG_EXEC
  "$HERE/gates.sh" "$@"
}

step_destroy() { hf destroy; }

step_delete() { kubeconfig_guard; minikube -p "$DS_MK_PROFILE" delete; }

step_all() {
  local t0 t times=()
  t0=$(date +%s)
  run() {
    t=$(date +%s); echo; echo "######## $* ($(date -u +%T)Z)"
    "$@"
    times+=("$(printf '%-24s %4ss' "${1#step_} ${2:-}" "$(( $(date +%s) - t ))")")
  }
  run step_cluster
  run step_certs
  run step_coredns
  run step_secrets
  if [ "$DS_MK_PLATFORM" = bundled ]; then run step_platform; else run step_issuer; fi
  run step_images
  run step_databases
  [ "$DS_MK_PLATFORM" = bundled ] && run step_realm
  run step_namespaces
  run step_configmaps
  run step_apply
  for p in "${PARTICIPANTS[@]}"; do run step_enrol "$p"; done
  run step_collectors
  run step_data_plane
  echo; echo "######## timings"; printf '%s\n' "${times[@]}"
  echo "total                    $(( $(date +%s) - t0 ))s"
}

main() {
  local cmd=${1:-}; shift || true
  case "$cmd" in
    cluster|delete|certs|secrets|build-images|realm-env) "step_${cmd//-/_}" "$@" ;;
    all) kubeconfig_guard; step_all ;;
    coredns|platform|issuer|images|databases|realm|namespaces|configmaps|apply|enrol|collectors|data-plane|test|gates|destroy)
      guard; "step_${cmd//-/_}" "$@" ;;
    guard) guard; echo "context $DS_MK_PROFILE, local API server" ;;
    *) sed -n '2,36p' "$0"; exit 2 ;;
  esac
}

main "$@"
