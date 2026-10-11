# shellcheck shell=bash
# The configuration and guards shared by helm/minikube/minikube.sh (the cluster),
# standalone.sh (ds without a host platform) and gates.sh. Sourced, never run.
# docs/deployment/local-cluster.md is the procedure.
#
# Every DS_MK_* value is a generic default a deployment overrides from its own
# environment (its rehearsal binding). What the releases are made of (participants,
# their roles and switches, the seed, the governance) is not here: it is the values,
# helm/minikube/values.yaml.gotmpl for ds's own `minikube` environment.

MK_HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# A fixed file of its own (gitignored), so a lost shell or scratch directory does not lose
# the cluster's credentials, and a shell without KUBECONFIG never falls back to the
# machine's default kubeconfig.
export KUBECONFIG=${KUBECONFIG:-$MK_HERE/.minikube.kubeconfig}
HELM_DIR=$(cd "$MK_HERE/.." && pwd)
DS_SRC=$(cd "$HELM_DIR/.." && pwd)

# ── The cluster (minikube.sh) ──────────────────────────────────────────────────
DS_MK_PROFILE=${DS_MK_PROFILE:-ds-minikube}
DS_MK_K8S_VERSION=${DS_MK_K8S_VERSION:-v1.33.0}
DS_MK_CPUS=${DS_MK_CPUS:-8}
DS_MK_MEMORY=${DS_MK_MEMORY:-24g}
DS_MK_DOMAIN=${DS_MK_DOMAIN:-ds.test}               # under .test: CoreDNS forwards it
DS_MK_CA_DIR=${DS_MK_CA_DIR:-$MK_HERE/.certs}        # ca.crt + ca.key
DS_MK_ISSUER=${DS_MK_ISSUER:-ds-minikube-ca}
DS_MK_IMAGE_TAG=${DS_MK_IMAGE_TAG:-minikube}
DS_IMAGES=(connector identity-registry provenance portal edc-connector dataset-api-mock)
OAUTH2_PROXY_IMAGE=quay.io/oauth2-proxy/oauth2-proxy:v7.11.0

# ── The releases and the stand-in platform (standalone.sh, gates.sh) ───────────
DS_MK_PLATFORM_NS=${DS_MK_PLATFORM_NS:-ds-platform}
DS_MK_HELMFILE_DIR=${DS_MK_HELMFILE_DIR:-$HELM_DIR}  # where `helmfile` runs
DS_MK_HELMFILE_ENV=${DS_MK_HELMFILE_ENV:-minikube}
DS_MK_VALUES=${DS_MK_VALUES:-$MK_HERE/values.yaml.gotmpl}
DS_MK_SECRETS=${DS_MK_SECRETS:-$MK_HERE/secrets.yaml}
DS_MK_BINDING=${DS_MK_BINDING:-$MK_HERE/binding}     # seed/, governance/<p>/, keycloak/
DS_MK_CONSUMER=${DS_MK_CONSUMER:-example-rec}        # the gates' consumer
DS_MK_PROVIDER=${DS_MK_PROVIDER:-example-dso}        # the gates' provider and holder
DS_MK_AUTHORITY_NS=${DS_MK_AUTHORITY_NS:-ds-authority}
DS_MK_PREFIX=${DS_MK_PREFIX:-ds-}
DS_MK_DATA_PLANE_NS=${DS_MK_DATA_PLANE_NS:-$DS_MK_PLATFORM_NS}
DS_MK_TOKEN_URL=${DS_MK_TOKEN_URL:-https://keycloak.$DS_MK_DOMAIN/realms/dataspaces/protocol/openid-connect/token}
DS_MK_PG_EXEC=${DS_MK_PG_EXEC:-kubectl exec -i -n $DS_MK_PLATFORM_NS ds-pg-1 -c postgres -- psql -v ON_ERROR_STOP=1 -q -U postgres}
DS_MK_SYNC_IMAGE=${DS_MK_SYNC_IMAGE:-ghcr.io/celine-eu/celine-policies:v1.7.0}
export DS_IMAGE_TAG=$DS_MK_IMAGE_TAG

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

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

# timed <step functions...>: runs each, then prints the timings.
timed() {
  local t0 t times=() f
  t0=$(date +%s)
  for f in "$@"; do
    t=$(date +%s); echo; echo "######## ${f#step_} ($(date -u +%T)Z)"
    "$f"
    times+=("$(printf '%-24s %4ss' "${f#step_}" "$(( $(date +%s) - t ))")")
  done
  echo; echo "######## timings"; printf '%s\n' "${times[@]}"
  echo "total                    $(( $(date +%s) - t0 ))s"
}
