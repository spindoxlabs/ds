#!/usr/bin/env bash
# A local minikube cluster for the ds charts: the cluster, a local CA, in-cluster DNS
# for the dataspace's hosts, and the ds images built from this checkout. Nothing of
# ds itself is installed here: the releases are the helmfile's (`helmfile -e
# minikube apply`), and a host platform (Postgres, a realm, cert-manager) is either a
# deployment's own infrastructure or ds's stand-in, helm/minikube/standalone.sh.
# docs/deployment/local-cluster.md is the procedure; `task helm:minikube:*` runs these.
#
#   helm/minikube/minikube.sh <step> [args]
#   (KUBECONFIG defaults to helm/minikube/.minikube.kubeconfig, gitignored; set it to use
#   another file of its own, never ~/.kube/config)
#
# Steps (`all` runs cluster, certs, coredns, images, in this order, and times each):
#   cluster        the minikube profile ($DS_MK_PROFILE), written into $KUBECONFIG only
#   certs          a local CA in $DS_MK_CA_DIR (created once, then reused: the images trust it)
#   coredns        `.test` names resolve, in-cluster, to the node (ingress-dns)
#   issuer         a CA ClusterIssuer over $DS_MK_CA_DIR for the ds hosts (needs
#                  cert-manager: the host platform's, or `standalone.sh platform`)
#   build-images [svc...]  build the ds images from this checkout (no cluster needed)
#   images         load them into the node, each with the local-CA layer
#   delete         minikube delete of the profile
#   guard          check the context is $DS_MK_PROFILE on a local API server
#
# Configuration: helm/minikube/env.sh (DS_MK_*). Every step that touches the cluster
# refuses unless the kubectl context is $DS_MK_PROFILE and its API server is local.
set -euo pipefail

# shellcheck source=env.sh
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
HERE=$MK_HERE

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

step_delete() { kubeconfig_guard; minikube -p "$DS_MK_PROFILE" delete; }

main() {
  local cmd=${1:-}; shift || true
  case "$cmd" in
    cluster|delete|certs|build-images) "step_${cmd//-/_}" "$@" ;;
    all) kubeconfig_guard; timed step_cluster step_certs step_coredns step_images ;;
    coredns|issuer|images) guard; "step_${cmd//-/_}" "$@" ;;
    guard) guard; echo "context $DS_MK_PROFILE, local API server" ;;
    *) sed -n '2,26p' "$0"; exit 2 ;;
  esac
}

main "$@"
