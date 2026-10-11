#!/usr/bin/env bash
# ds on the local cluster without a host platform: the stand-ins a deployment's own
# infrastructure provides elsewhere (cert-manager, CloudNativePG with one cluster and
# the ds databases, Keycloak with ds's dev realm, a data plane), the generated secrets,
# and the ds releases. The cluster itself is helm/minikube/minikube.sh. A deployment
# that has its own platform (its infrastructure on the same minikube) uses none of the
# stand-in steps: only the helmfile, through its own values and secrets.
# docs/deployment/local-cluster.md is the procedure; `task helm:standalone:*` runs these.
#
#   helm/minikube/standalone.sh <step> [args]
#
# Steps (`all` runs: minikube.sh all, secrets, platform, issuer, databases, realm,
# apply, data-plane; timed):
#   secrets        generate $DS_MK_SECRETS from the values if it does not exist (an
#                  enrolment code per participant with enrolment on, a collector
#                  secret per collector)
#   platform       cert-manager, CloudNativePG + one cluster, Keycloak with ds's dev realm
#   databases      one database and owner role per service ($DS_MK_PG_EXEC)
#   realm          sync the ds clients into the bundled realm
#   realm-env      print the realm's client secrets as env lines (pipe only)
#   apply          helmfile apply, every release. The seed, the governance, the
#                  enrolment and the collector pair are the charts' (values), so there
#                  is no ConfigMap, enrolment or restart step
#   data-plane     the data-plane stand-in in $DS_MK_DATA_PLANE_NS
#   test           helm test, every release
#   gates [gate..] the gates (helm/minikube/gates.sh)
#   destroy        helmfile destroy (the ds releases only)
#
# Configuration: helm/minikube/env.sh (DS_MK_*). Every step that touches the cluster
# refuses unless the kubectl context is $DS_MK_PROFILE and its API server is local.
set -euo pipefail

# shellcheck source=env.sh
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
HERE=$MK_HERE

# ── Steps ──────────────────────────────────────────────────────────────────────

step_platform() {
  helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
  helm repo add cnpg https://cloudnative-pg.github.io/charts >/dev/null 2>&1 || true
  helm repo update jetstack cnpg >/dev/null
  helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
    --version v1.16.3 --set crds.enabled=true --wait --timeout 600s
  helm upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace \
    --version 0.26.0 --wait --timeout 600s
  "$HERE/minikube.sh" issuer
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

step_secrets() {
  # The collectors and the enrolment codes follow the values' switches.
  uv run -q --no-project --with pyyaml --with cryptography python "$HELM_DIR/tools/generate_secrets.py" \
    --values "$DS_MK_VALUES" --out "$DS_MK_SECRETS" "$@"
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

step_apply() { hf apply --suppress-diff "$@"; }

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

step_gates() { "$HERE/gates.sh" "$@"; }

step_destroy() { hf destroy; }

step_cluster() { "$HERE/minikube.sh" all; }
step_issuer() { "$HERE/minikube.sh" issuer; }

main() {
  local cmd=${1:-}; shift || true
  case "$cmd" in
    secrets|realm-env) "step_${cmd//-/_}" "$@" ;;
    all) kubeconfig_guard; timed step_cluster step_secrets step_platform step_databases step_realm step_apply step_data_plane ;;
    platform|databases|realm|apply|data-plane|test|gates|destroy) guard; "step_${cmd//-/_}" "$@" ;;
    *) sed -n '2,31p' "$0"; exit 2 ;;
  esac
}

main "$@"
