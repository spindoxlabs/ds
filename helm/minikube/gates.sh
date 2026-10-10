#!/usr/bin/env bash
# The gates of a local cluster (helm/minikube/minikube.sh), each proven to fail when its
# surface is broken: `helm test`, the anchor's bootstrap (owners and collectors), the
# `helm test` negatives, the install checks (pods, sync Jobs, the EDR key, a transfer
# through the data-plane stand-in, a governance change), the secret policy's refusals,
# every guard on the cluster, a key rotation, and the did:web internal allowance
# (ADR-0029). Every red case is put back before the next gate starts.
#
#   helm/minikube/minikube.sh gates [gate...]     (configuration: minikube.sh's DS_MK_*)
#
# gates: helm-test t2.3 t2.4 t4.1 t5.1 t5.2 t5.3 consumer-list t5.5 allowance
#        allowance-services render-negatives pod-negatives rotation; all (every gate, in
#        this order)
#
# Each check prints `PASS <gate>: <evidence>` or `FAIL <gate>: <evidence>` (a known gap
# prints `GAP`); the exit code is the number of failures. The on-cluster negatives mutate
# one release with `helm upgrade --reuse-values --set …` (helm directly: the render
# policy would refuse the value first, which `render-negatives` shows), read the
# refusal from the new pod, then `helm rollback`. Nothing secret is printed.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
CHARTS=$(cd "$HERE/../charts" && pwd)
DS_SRC=$(cd "$HERE/../.." && pwd)
: "${DS_MK_PROFILE:?run through minikube.sh gates}"
SECRETS=$DS_MK_SECRETS
B=$DS_MK_BINDING
CON=$DS_MK_CONSUMER PRO=$DS_MK_PROVIDER DOMAIN=$DS_MK_DOMAIN
AUTH=$DS_MK_AUTHORITY_NS NCON=$DS_MK_PREFIX$DS_MK_CONSUMER NPRO=$DS_MK_PREFIX$DS_MK_PROVIDER
DPNS=$DS_MK_DATA_PLANE_NS
CON_DB=connector_${CON//-/_}
FAILS=0

"$HERE/minikube.sh" guard >/dev/null || exit 9
hf() { (cd "$DS_MK_HELMFILE_DIR" && DS_MK_NODE_IP=$(minikube -p "$DS_MK_PROFILE" ip) helmfile -e "$DS_MK_HELMFILE_ENV" "$@"); }

pass() { echo "PASS $1: $2"; }
fail() { echo "FAIL $1: $2"; FAILS=$((FAILS + 1)); }
sec() { uv run -q --no-project --with pyyaml python -c "
import yaml, json
d = yaml.safe_load(open('$SECRETS')); s = d['secrets']; p = s['participants']
PRO, CON = '$PRO', '$CON'
print($1, end='')"; }
# has <pattern> <command...>: the command's whole output matches. Not `command | grep -q`:
# grep exits at the first match, the command gets SIGPIPE, and under pipefail the
# pipeline then reports failure for a match.
has() { local pat=$1 out; shift; out=$("$@" 2>&1); grep -qE -- "$pat" <<<"$out"; }
newest_pod() { kubectl get pods -n "$1" -l "app.kubernetes.io/instance=$2" --sort-by=.metadata.creationTimestamp -o name | grep -v -- -test- | tail -1; }
helm_test() { helm test -n "$1" "$2" --logs --timeout 180s 2>&1; }
logs_of() {  # every container, current and previous, ANSI stripped
  local ns=$1 pod=$2 c
  for c in $(kubectl get "$pod" -n "$ns" -o jsonpath='{.spec.initContainers[*].name} {.spec.containers[*].name}' 2>/dev/null); do
    kubectl logs -n "$ns" "$pod" -c "$c" 2>/dev/null; kubectl logs -n "$ns" "$pod" -c "$c" --previous 2>/dev/null
  done | sed 's/\x1b\[[0-9;]*m//g'
}

# In the data-plane stand-in pod: MODE=<jwks|flow|query|pep> flow.py.
flow() {
  local mode=$1 extra=${2:-}
  { sec "p[CON]['organisationClientSecret']"; echo; cat "$HERE/flow.py"; } \
    | kubectl exec -i -n "$DPNS" deploy/ds-data-plane -- env MODE="$mode" EXPECT_X="$extra" \
        CONSUMER="$CON" PROVIDER="$PRO" DOMAIN="$DOMAIN" CONSUMER_NS="$NCON" PROVIDER_NS="$NPRO" python -c \
      "import sys, os; os.environ['REC_ORG_SECRET'] = sys.stdin.readline().strip(); exec(sys.stdin.read())" 2>&1
}

# A pod-level negative: mutate, find the new pod's refusal, roll back.
#   refuses <gate> <ns> <release> <chart> "<regex1>|||<regex2>..." -- <helm args...>
refuses() {
  local gate=$1 ns=$2 rel=$3 chart=$4 want=$5; shift 6
  local before old pod out missing="" re
  before=$(helm history "$rel" -n "$ns" -o json | jq '.[-1].revision')
  old=$(kubectl get pods -n "$ns" -l "app.kubernetes.io/instance=$rel" -o name | tr '\n' ' ')
  helm upgrade "$rel" "$CHARTS/$chart" -n "$ns" --reuse-values --no-hooks "$@" >/dev/null 2>&1 || true
  pod=""
  for _ in $(seq 1 30); do
    pod=$(kubectl get pods -n "$ns" -l "app.kubernetes.io/instance=$rel" -o name | grep -v -- -test- | grep -vxF -f <(tr ' ' '\n' <<<"$old" | grep .) | head -1)
    [ -n "$pod" ] && break; sleep 2
  done
  out=""
  for _ in $(seq 1 60); do
    out=$(logs_of "$ns" "$pod")
    missing=""
    while IFS= read -r re; do grep -qE -- "$re" <<<"$out" || missing+="[$re] "; done < <(sed 's/|||/\n/g' <<<"$want")
    [ -z "$missing" ] && break
    sleep 3
  done
  helm rollback "$rel" "$before" -n "$ns" --no-hooks --wait=watcher --timeout 300s >/dev/null 2>&1 \
    || echo "  (rollback of $rel to $before reported an error)"
  kubectl rollout status deploy/"$rel" -n "$ns" --timeout=300s >/dev/null 2>&1
  if [ -z "$missing" ]; then
    pass "$gate" "$(grep -oE -- "$(sed 's/|||/|/g' <<<"$want")" <<<"$out" | sort -u | tr '\n' ';' | cut -c1-400)"
  else
    fail "$gate" "${pod#pod/} did not show $missing"
  fi
}

gate_helm_test() {
  local r ns name out
  for r in $(hf list --output json 2>/dev/null | jq -r '.[] | select(.name != "ds-namespaces") | "\(.namespace)/\(.name)"'); do
    ns=${r%/*} name=${r#*/}
    out=$(helm_test "$ns" "$name"); rc=$?
    if ! grep -q "TEST SUITE: *None" <<<"$out" && grep -q "TEST SUITE:" <<<"$out"; then
      [ $rc -eq 0 ] && pass "helm-test $name" "$(grep -A1 'POD LOGS' <<<"$out" | tail -1)" \
                    || fail "helm-test $name" "$(grep -E 'Phase|POD LOGS' -A1 <<<"$out" | tr '\n' ' ' | cut -c1-300)"
    else
      echo "NOTE helm-test $name: the chart defines no test"
    fi
  done
}

gate_t2_3() {
  # `org apply` onboards exactly the owners the governance exposes; the chart's
  # `owner import` first changes nothing. A third owner no governance names is skipped;
  # a governance file exposing nothing is a refusal, not "zero onboarded, exit 0".
  local pod t out
  pod=$(newest_pod "$AUTH" ds-identity-registry); t=$(mktemp -d)
  cp "$B/seed/owners.yaml" "$t/owners-t23.yaml"
  printf '  - id: example-other\n    type: schema:Organization\n    name: An owner no governance names\n    did: did:web:example-other.%s\n' "$DOMAIN" >> "$t/owners-t23.yaml"
  cp "$B/governance/$CON/governance.yaml" "$t/$CON.governance.yaml"
  cp "$B/governance/$PRO/governance.yaml" "$t/$PRO.governance.yaml"
  sed 's/expose: true/expose: false/' "$B/governance/$PRO/governance.yaml" > "$t/none.governance.yaml"
  kubectl cp "$t" "$AUTH/${pod#pod/}:/tmp/t23" -c identity-registry; rm -rf "$t"
  out=$(kubectl exec -n "$AUTH" "$pod" -c identity-registry -- env CON="$CON" PRO="$PRO" sh -c 'cd /tmp/t23
    ir-cli owner import --file owners-t23.yaml
    ir-cli org apply --file owners-t23.yaml --governance $CON.governance.yaml --governance $PRO.governance.yaml --verified-by ds-mk-t23 --evidence-ref t23 --dry-run; echo "rc=$?"' 2>&1)
  echo "$out" | sed 's/^/  /'
  if grep -q "2 organisation(s) applied, 0 changed, 1 skipped, 0 failed" <<<"$out" && grep -q "governance does not name it" <<<"$out"; then
    pass t2.3 "the two exposed owners applied (unchanged after owner import), example-other skipped"
  else fail t2.3 "unexpected org apply report"; fi
  out=$(kubectl exec -n "$AUTH" "$pod" -c identity-registry -- sh -c 'cd /tmp/t23
    ir-cli org apply --file owners-t23.yaml --governance none.governance.yaml --verified-by ds-mk-t23 --evidence-ref t23 --dry-run; echo "rc=$?"' 2>&1)
  if grep -q "rc=1" <<<"$out" && grep -q "nothing would be onboarded" <<<"$out"; then
    pass "t2.3 red" "$(grep -o 'no exposed dataset.*' <<<"$out" | cut -c1-160)"
  else fail "t2.3 red" "$out"; fi
  # owner import is not a dry run: take the test owner out again.
  kubectl exec -n "$AUTH" "$pod" -c identity-registry -- sh -c 'ir-cli owner remove --id example-other >/dev/null; rm -rf /tmp/t23'
}

gate_t2_4() {
  # The collector pair bootstrap.sh adds, and a revocation that survives it: revoke,
  # restart the anchor (its bootstrap runs `collector add` again), still revoked; then
  # the explicit reinstatement puts it back in force.
  local out pod
  local pair="--holder-did did:web:$PRO.$DOMAIN --collector-did did:web:$CON.$DOMAIN"
  out=$(kubectl exec -n "$AUTH" deploy/ds-identity-registry -c identity-registry -- ir-cli collector list 2>&1)
  grep -q "did:web:$CON.$DOMAIN → did:web:$PRO.$DOMAIN  active" <<<"$out" \
    && pass t2.4 "collector pair from bootstrap.sh active" || fail t2.4 "$out"
  # shellcheck disable=SC2086
  kubectl exec -n "$AUTH" deploy/ds-identity-registry -c identity-registry -- ir-cli collector revoke \
    $pair --reason "gate T2.4: the agreement ended" --by gate-t2.4 >/dev/null
  kubectl rollout restart -n "$AUTH" deploy/ds-identity-registry >/dev/null
  kubectl rollout status -n "$AUTH" deploy/ds-identity-registry --timeout=300s >/dev/null
  pod=$(newest_pod "$AUTH" ds-identity-registry)
  out=$(kubectl exec -n "$AUTH" "$pod" -c identity-registry -- ir-cli collector list 2>&1)
  if grep -q "did:web:$CON.$DOMAIN → did:web:$PRO.$DOMAIN  revoked" <<<"$out" \
    && has "Consent collector revoked, left unchanged: .*revoked by gate-t2.4 at .*the agreement ended" \
      kubectl logs -n "$AUTH" "$pod" -c bootstrap; then
    pass "t2.4 revoked survives restart" "after the anchor restart the pair is still revoked; bootstrap: $(kubectl logs -n "$AUTH" "$pod" -c bootstrap | grep -o 'Consent collector revoked, left unchanged.*' | cut -c1-200)"
  else fail "t2.4 revoked survives restart" "$(echo $out)"; fi
  # shellcheck disable=SC2086
  out=$(kubectl exec -n "$AUTH" deploy/ds-identity-registry -c identity-registry -- ir-cli collector reinstate \
    $pair --reason "gate T2.4: renewed" --by gate-t2.4 2>&1)
  if grep -q "reinstated" <<<"$out" \
    && has "did:web:$CON.$DOMAIN → did:web:$PRO.$DOMAIN  active" \
      kubectl exec -n "$AUTH" deploy/ds-identity-registry -c identity-registry -- ir-cli collector list; then
    pass "t2.4 reinstate" "ir-cli collector reinstate: active again ($out)"
  else fail "t2.4 reinstate" "$out"; fi
}

gate_t4_1() {
  local out before
  # a: the DID document's id is not the release's participant DID.
  before=$(helm history ds-edc-$PRO -n "$NPRO" -o json | jq '.[-1].revision')
  helm upgrade ds-edc-$PRO "$CHARTS/ds-edc" -n "$NPRO" --reuse-values --no-hooks \
    --set participant.did=did:web:wrong.$DOMAIN --wait=watcher --timeout 300s >/dev/null 2>&1
  out=$(helm_test "$NPRO" ds-edc-$PRO)
  grep -q "Phase: *Failed" <<<"$out" && pass "t4.1 a (wrong DID id)" "$(grep -o 'serves a DID document.*' <<<"$out" | cut -c1-160)" || fail "t4.1 a" "$out"
  helm rollback ds-edc-$PRO "$before" -n "$NPRO" --no-hooks --wait=watcher --timeout 300s >/dev/null 2>&1
  # b: /join behind the auth wall.
  kubectl get ingress ds-portal-$CON-public -n "$NCON" -o json \
    | jq 'del(.metadata.resourceVersion,.metadata.uid,.metadata.creationTimestamp,.metadata.generation,.metadata.managedFields,.status)' > /tmp/.ds-mk-portal-public.json
  kubectl delete ingress ds-portal-$CON-public -n "$NCON" >/dev/null; sleep 5
  out=$(helm_test "$NCON" ds-portal-$CON)
  grep -q "Phase: *Failed" <<<"$out" && pass "t4.1 b (/join walled)" "$(grep -o '/join answered.*' <<<"$out" | cut -c1-120)" || fail "t4.1 b" "$out"
  kubectl create -f /tmp/.ds-mk-portal-public.json >/dev/null; rm -f /tmp/.ds-mk-portal-public.json; sleep 5
  # c: the catalogue lacks an asset the governance exposes (ConfigMap changed, no sync).
  t45_governance_extra > /tmp/.ds-mk-gov.yaml
  kubectl create configmap $PRO-governance -n "$NPRO" --from-file=governance.yaml=/tmp/.ds-mk-gov.yaml --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  out=$(helm_test "$NPRO" ds-connector-$PRO)
  grep -q "Phase: *Failed" <<<"$out" && pass "t4.1 c (catalogue ≠ governance)" "$(grep -o 'catalogue: .*' <<<"$out" | head -1)" || fail "t4.1 c" "$out"
  "$HERE/minikube.sh" configmaps >/dev/null; rm -f /tmp/.ds-mk-gov.yaml
  # d: the participant registry scaled to zero.
  kubectl scale deploy ds-identity-registry-$PRO -n "$NPRO" --replicas=0 >/dev/null
  kubectl wait --for=delete pod -l app.kubernetes.io/instance=ds-identity-registry-$PRO -n "$NPRO" --timeout=120s >/dev/null 2>&1
  out=$(helm_test "$NPRO" ds-identity-registry-$PRO)
  grep -q "Phase: *Failed" <<<"$out" && pass "t4.1 d (registry at zero)" "test Pod failed" || fail "t4.1 d" "$out"
  kubectl scale deploy ds-identity-registry-$PRO -n "$NPRO" --replicas=1 >/dev/null
  kubectl rollout status deploy/ds-identity-registry-$PRO -n "$NPRO" --timeout=300s >/dev/null
  # every test green again
  for r in "$NPRO/ds-edc-$PRO" "$NCON/ds-portal-$CON" "$NPRO/ds-connector-$PRO" "$NPRO/ds-identity-registry-$PRO"; do
    has "Phase: *Succeeded" helm_test "${r%/*}" "${r#*/}" || fail "t4.1 restore" "${r#*/} not green after restore"
  done
  pass "t4.1 restore" "all four tests green again"
}

t45_governance_extra() {  # the DSO governance plus a second exposed dataset
  cat "$B/governance/$PRO/governance.yaml"
  cat <<EOF

  datasets.gold.om_weather_features:
    title: "Weather Features (Gold), DSO copy"
    description: Gates only, the second exposed dataset of a governance change.
    license: CC-BY-4.0
    access_level: open
    classification: green
    tags: [weather, gold]
    source_system: local stand-in
    dataspace:
      expose: true
      medallion: gold
      purpose: [GridMonitoring]
      asset:
        id: "datasets.gold.om_weather_features"
        content_type: "application/json"
      data_address:
        type: HttpData
        base_url: "http://ds-data-plane.$DPNS.svc.cluster.local:30002/query"
        proxy_path: false
        proxy_query_params: true
EOF
}

gate_t5_1() {
  local notready jobs
  # Pods of a release (not test or hook Pods, not one still terminating) whose Ready
  # condition is not True.
  notready=$(for ns in $AUTH $NCON $NPRO; do kubectl get pods -n "$ns" -o json | jq -r '.items[]
    | select(.metadata.deletionTimestamp == null)
    | select(.metadata.name | test("-test-|-sync-") | not)
    | select([.status.conditions[]? | select(.type == "Ready" and .status == "True")] | length == 0)
    | .metadata.name'; done)
  [ -z "$notready" ] && pass t5.1 "every pod Ready ($(for ns in $AUTH $NCON $NPRO; do kubectl get pods -n $ns --no-headers | grep -vc -- -test-; done | paste -sd+ | bc) pods)" || fail t5.1 "not ready: $notready"
  for ns in $NCON $NPRO; do
    p=${ns#$DS_MK_PREFIX}
    # The publishing hook fails its release on errors or an empty publish, so a Completed
    # Job means a non-empty sync; the catalogue test shows what it published.
    jobs=$(kubectl get events -n "$ns" --field-selector involvedObject.kind=Job,reason=Completed -o name | wc -l)
    cat=$(helm_test "$ns" "ds-connector-$p" | grep -o "catalogue: .*" | head -1)
    [ "$jobs" -ge 1 ] && grep -qE "catalogue: [1-9][0-9]* asset\(s\); governance exposes [1-9]" <<<"$cat" \
      && pass "t5.1 sync $p" "publishing Job Completed ($jobs); $cat" || fail "t5.1 sync $p" "jobs=$jobs $cat"
  done
  echo "  (T5.1's red case, a withheld or placeholder secret refused by name, is pod-negatives)"
}

gate_t5_2() {
  local x out
  x="$PRO=$(sec "json.loads(p[PRO]['edcVault']['edrSigningPublicJwk'])['x']"),$CON=$(sec "json.loads(p[CON]['edcVault']['edrSigningPublicJwk'])['x']")"
  out=$(flow jwks "$x"); echo "$out" | grep -v '^RESULT' | sed 's/^/  /'
  grep -q "RESULT jwks PASS" <<<"$out" && pass t5.2 "kid = participant-private-key, x = the configured public half, no d, 401 anonymous" || fail t5.2 "$(grep RESULT <<<"$out")"
  kubectl set env -n "$NPRO" deploy/ds-connector-$PRO -c connector CONNECTOR_EDC_VAULT_FILE- >/dev/null
  kubectl rollout status -n "$NPRO" deploy/ds-connector-$PRO --timeout=300s >/dev/null
  out=$(flow jwks "$x")
  grep -q "$PRO 503" <<<"$out" && pass "t5.2 red" "vault file unset: 503" || fail "t5.2 red" "$(grep "$PRO" <<<"$out")"
  kubectl rollout undo -n "$NPRO" deploy/ds-connector-$PRO >/dev/null
  kubectl rollout status -n "$NPRO" deploy/ds-connector-$PRO --timeout=300s >/dev/null
}

gate_t5_3() {
  local out np=/tmp/.ds-mk-np.yaml
  out=$(flow flow); echo "$out" | grep -v '^RESULT' | sed 's/^/  /'
  grep -q "RESULT flow PASS" <<<"$out" && pass t5.3 "$(grep -o 'PASS .*' <<<"$out" | cut -c6-)" || fail t5.3 "$(grep RESULT <<<"$out")"
  has 'POST /internal/dataplane/authorize HTTP/1.1\\" 200' kubectl logs -n "$NPRO" deploy/ds-connector-$PRO -c connector --since=3m \
    && pass "t5.3 PEP" "the DSO connector answered /internal/dataplane/authorize 200 to the stand-in" || fail "t5.3 PEP" "no authorize 200 in the DSO connector log"
  kubectl get networkpolicy ds-connector-$PRO-from-callers -n "$NPRO" -o yaml > $np
  kubectl delete networkpolicy ds-connector-$PRO-from-callers -n "$NPRO" >/dev/null
  out=$(flow pep)
  grep -q "RESULT pep PASS" <<<"$out" && pass "t5.3 red" "without the ingressFrom policy: $(grep -o 'PASS .*' <<<"$out" | cut -c6-)" || fail "t5.3 red" "$(grep RESULT <<<"$out")"
  kubectl apply -f $np >/dev/null; rm -f $np
  out=$(flow query); grep -q "RESULT query PASS" <<<"$out" && pass "t5.3 restored" "query 200 again" || fail "t5.3 restored" "$(grep RESULT <<<"$out")"
}

gate_t5_5() {
  local g="$B/governance/$PRO/governance.yaml" orig pod0 pod1 out sum0 sum1
  orig=$(mktemp); cp "$g" "$orig"
  pod0=$(newest_pod "$NPRO" ds-connector-$PRO)
  # red: the ConfigMap changes, the checksum does not: nothing rolls, no sync.
  t45_governance_extra > /tmp/.ds-mk-gov.yaml
  kubectl create configmap $PRO-governance -n "$NPRO" --from-file=governance.yaml=/tmp/.ds-mk-gov.yaml --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  (hf -l name=ds-connector-$PRO apply --skip-deps --suppress-diff >/dev/null 2>&1)
  [ "$(newest_pod "$NPRO" ds-connector-$PRO)" = "$pod0" ] && pass "t5.5 red" "ConfigMap changed without the checksum: same pod ${pod0#pod/}, no upgrade" || fail "t5.5 red" "the connector rolled"
  # green: the governance file changes (the checksum follows it).
  cp /tmp/.ds-mk-gov.yaml "$g"; rm -f /tmp/.ds-mk-gov.yaml
  sum0=$(kubectl get deploy ds-connector-$PRO -n "$NPRO" -o jsonpath='{.spec.template.metadata.annotations.checksum/governance}')
  "$HERE/minikube.sh" configmaps >/dev/null
  (hf -l name=ds-connector-$PRO apply --skip-deps --suppress-diff >/dev/null 2>&1)
  pod1=$(newest_pod "$NPRO" ds-connector-$PRO)
  sum1=$(kubectl get deploy ds-connector-$PRO -n "$NPRO" -o jsonpath='{.spec.template.metadata.annotations.checksum/governance}')
  out=$(helm_test "$NPRO" ds-connector-$PRO)
  if [ "$pod1" != "$pod0" ] && [ "$sum1" != "$sum0" ] && grep -q "catalogue: 2 asset(s); governance exposes 2" <<<"$out"; then
    pass t5.5 "checksum ${sum0:0:8}→${sum1:0:8}, connector rolled, sync re-ran, catalogue 2 = governance 2"
  else fail t5.5 "pod ${pod1#pod/} sum ${sum1:0:8} test: $(grep -o 'catalogue: .*' <<<"$out")"; fi
  cp "$orig" "$g"; rm -f "$orig"
  "$HERE/minikube.sh" configmaps >/dev/null
  (hf -l name=ds-connector-$PRO apply --skip-deps --suppress-diff >/dev/null 2>&1)
  has "Withdrew dataset datasets.gold.om_weather_features" kubectl logs -n "$NPRO" deploy/ds-connector-$PRO -c connector \
    && has "catalogue: 1 asset\(s\); governance exposes 1" helm_test "$NPRO" ds-connector-$PRO \
    && pass "t5.5 revert" "governance reverted: the sync withdrew the extra asset, catalogue 1" || fail "t5.5 revert" "catalogue not back to 1"
}

gate_consumer_list() {
  # The organisation lists its own consumer requests with `negotiations:read` alone
  # (ds_auth.ORGANISATION_READ_SCOPES, synced into the realm); red: no negotiation
  # scope is refused, and the read-only token cannot negotiate. A repeated negotiation
  # answers 409 naming the request_id the revoke route takes. Runs after t5.3.
  local out
  out=$(flow list); echo "$out" | grep -v '^RESULT' | sed 's/^/  /'
  grep -q "RESULT list PASS" <<<"$out" && pass consumer-list "$(grep -o 'PASS .*' <<<"$out" | cut -c6-)" \
    || fail consumer-list "$(grep RESULT <<<"$out")"
}

gate_allowance_services() {
  # ADR-0029, extended: the connector, provenance and the EDC fetch did:web behind the
  # same guard. With the deployment's allowance a person route's issuer and the DCP
  # counterparty resolve (t5.3's flow passes, the logs say the allowance is active);
  # without it each refuses the node's private address.
  local ip out logs
  ip=$(minikube -p "$DS_MK_PROFILE" ip)
  for rel in ds-connector-$CON ds-provenance-$CON; do
    has "did:web internal allowance active: hosts under .$DOMAIN may resolve to $ip/32" kubectl logs -n "$NCON" deploy/$rel \
      && pass "allowance $rel" "start log: did:web internal allowance active ($ip/32)" \
      || fail "allowance $rel" "no allowance line in the log"
  done
  has "did:web internal allowance active: hosts under .$DOMAIN may resolve to $ip/32" kubectl logs -n "$NCON" deploy/ds-edc-$CON \
    && pass "allowance ds-edc-$CON" "start log: did:web internal allowance active ($ip/32)" \
    || fail "allowance ds-edc-$CON" "no allowance line in the EDC log"
  # Connector/provenance resolver, in the pod, without the allowance (dev=False, as the
  # pod runs) and with the pod's own settings: refused, then admitted (dialled).
  for rel in ds-connector-$CON ds-provenance-$CON; do
    out=$(kubectl exec -n "$NCON" deploy/$rel -- python -c "
import os
from ds_auth.address_guard import InternalAllowance
from ds_auth.did_web import DidWebResolver, DidResolutionError
did = 'did:web:trust-anchor.$DOMAIN'
pfx = 'CONNECTOR_' if 'connector' in '$rel' else 'PROVENANCE_'
allow = InternalAllowance.parse(os.environ.get(pfx + 'DID_WEB_INTERNAL_HOSTS', ''), os.environ.get(pfx + 'DID_WEB_INTERNAL_NETWORKS', ''))
try:
    DidWebResolver(dev=False).resolve(did); print('without: RESOLVED')
except DidResolutionError as e:
    print('without:', e)
try:
    doc = DidWebResolver(dev=False, allowance=allow).resolve(did); print('with: RESOLVED', doc['id'])
except DidResolutionError as e:
    print('with:', e)
" 2>&1)
    if grep -q "without: .*non-public address ($ip)" <<<"$out" && grep -q "with: RESOLVED did:web:trust-anchor.$DOMAIN" <<<"$out"; then
      pass "allowance $rel fetch" "without: $(grep -o 'resolves to a non-public address ([^)]*)' <<<"$out" | head -1); with: $(grep -o 'RESOLVED did:web:[^ ]*' <<<"$out")"
    else fail "allowance $rel fetch" "$(tr '\n' ' ' <<<"$out" | cut -c1-300)"; fi
  done
  # The EDC: drop the provider EDC's allowance (its ConfigMap property) and roll. The
  # provider resolves the consumer's DID to verify its token, so the consumer's flow is
  # refused at the first DSP call and the provider EDC logs the refusal. Restore.
  local cm=ds-edc-$PRO before
  before=$(kubectl get configmap "$cm" -n "$NPRO" -o json | jq 'del(.metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.managedFields)')
  jq '.data["edc.properties"] |= (split("\n") | map(select(startswith("ds.did.web.internal") | not)) | join("\n"))' <<<"$before" \
    | kubectl apply -f - >/dev/null
  kubectl rollout restart -n "$NPRO" deploy/ds-edc-$PRO >/dev/null
  kubectl rollout status -n "$NPRO" deploy/ds-edc-$PRO --timeout=300s >/dev/null
  out=$(flow flow)
  logs=$(kubectl logs -n "$NPRO" deploy/ds-edc-$PRO --since=5m 2>&1)
  if ! grep -q "RESULT flow PASS" <<<"$out" && grep -qE "resolves to a non-public address \($ip\)" <<<"$logs"; then
    pass "allowance ds-edc-$PRO red" "without the allowance: flow refused ($(grep RESULT <<<"$out" | cut -c1-120)); EDC: '$(grep -oE "[^ ]+ resolves to a non-public address \($ip\)" <<<"$logs" | head -1)'"
  else fail "allowance ds-edc-$PRO red" "$(grep RESULT <<<"$out") / no refusal in the EDC log"; fi
  kubectl apply -f - <<<"$before" >/dev/null
  kubectl rollout restart -n "$NPRO" deploy/ds-edc-$PRO >/dev/null
  kubectl rollout status -n "$NPRO" deploy/ds-edc-$PRO --timeout=300s >/dev/null
  out=$(flow flow)
  grep -q "RESULT flow PASS" <<<"$out" && pass "allowance ds-edc-$PRO restored" "flow passes again" \
    || fail "allowance ds-edc-$PRO restored" "$(grep RESULT <<<"$out")"
}

gate_allowance() {
  # ADR-0029 on the cluster. The dataspace's hosts resolve in-cluster to the node (a
  # private address); the anchor's resolver admits it only through the allowance the
  # values set. The provider re-enrols (a fresh code, `--force`) under three anchors:
  # without the allowance, with the suffix but an address outside the listed /32, and
  # with the deployment's own allowance. The first two must be refused, the third issued.
  local ip other out
  ip=$(minikube -p "$DS_MK_PROFILE" ip)
  other=$(awk -F. -v OFS=. '{ $4 = ($4 == 254 ? 253 : $4 + 1); print }' <<<"$ip")
  reenrol() {
    local code
    code=$(kubectl exec -n "$AUTH" deploy/ds-identity-registry -c identity-registry -- \
      ir-cli org enrolment-token --alias "$PRO" --roles provider --scope dataspaces.query --label gate-allowance 2>/dev/null)
    printf '%s\n' "$code" | kubectl exec -i -n "$NPRO" "deploy/ds-identity-registry-$PRO" -c identity-registry -- \
      sh -c 'read -r CODE; ir-cli participant init --force --code "$CODE"' 2>&1
  }
  anchor_env() {  # anchor_env <kubectl set env args...>; waits for the roll
    kubectl set env -n "$AUTH" deploy/ds-identity-registry -c identity-registry "$@" >/dev/null
    kubectl rollout status -n "$AUTH" deploy/ds-identity-registry --timeout=300s >/dev/null
  }
  anchor_env IDENTITY_REGISTRY_DID_WEB_INTERNAL_HOSTS- IDENTITY_REGISTRY_DID_WEB_INTERNAL_NETWORKS-
  out=$(reenrol)
  if grep -q "Enrolment refused" <<<"$out" && has "resolves to a non-public address" kubectl logs -n "$AUTH" deploy/ds-identity-registry -c identity-registry --since=2m; then
    pass "allowance red (none)" "without the setting: enrolment refused, anchor: 'resolves to a non-public address ($ip)'"
  else fail "allowance red (none)" "$(tail -1 <<<"$out")"; fi
  kubectl rollout undo -n "$AUTH" deploy/ds-identity-registry >/dev/null
  kubectl rollout status -n "$AUTH" deploy/ds-identity-registry --timeout=300s >/dev/null
  anchor_env IDENTITY_REGISTRY_DID_WEB_INTERNAL_NETWORKS="$other/32"
  out=$(reenrol)
  if grep -q "Enrolment refused" <<<"$out" && has "resolves to a non-public address" kubectl logs -n "$AUTH" deploy/ds-identity-registry -c identity-registry --since=2m; then
    pass "allowance red (wrong /32)" "suffix .$DOMAIN listed, network $other/32: enrolment refused"
  else fail "allowance red (wrong /32)" "$(tail -1 <<<"$out")"; fi
  kubectl rollout undo -n "$AUTH" deploy/ds-identity-registry >/dev/null
  kubectl rollout status -n "$AUTH" deploy/ds-identity-registry --timeout=300s >/dev/null
  out=$(reenrol)
  grep -q "Enrolled with .*ISSUED" <<<"$out" \
    && pass allowance "suffix .$DOMAIN + $ip/32: enrolment ISSUED; anchor log: $(kubectl logs -n "$AUTH" deploy/ds-identity-registry -c identity-registry | grep -o 'did:web internal allowance active: .*' | head -1 | cut -c1-120)" \
    || fail allowance "$(tail -1 <<<"$out")"
}

gate_render_negatives() {
  # The same file, mutated one way at a time: the parent helmfile's render (the secret
  # policy) and ds's preflight must each refuse, naming the key and printing no value.
  local backup t name expr out pf
  backup=$(mktemp); cp "$SECRETS" "$backup"; t=$(mktemp --suffix=.yaml)
  while IFS='|' read -r name expr; do
    PRO=$PRO CON=$CON DS_SRC=$DS_SRC uv run -q --no-project --with pyyaml python -c "
import yaml, json, glob, os
PRO, CON, DS_SRC = os.environ['PRO'], os.environ['CON'], os.environ['DS_SRC']
d = yaml.safe_load(open('$backup')); s = d['secrets']; p = s['participants']
$expr
open('$t', 'w').write(yaml.safe_dump(d, sort_keys=False))"
    cp "$t" "$SECRETS"
    out=$(hf template --skip-deps 2>&1 | grep -oE "error calling fail: secret policy: [^%]{0,160}" | head -1 | sed "s/^error calling fail: //")
    pf=$(cd "$DS_SRC" && uv run -q --no-project --with pyyaml python helm/tools/secrets_check.py "$t" 2>&1 | grep '✗' | head -1)
    if [ -n "$out" ] || [ "$name" = "client secret equals its id" ]; then
      [ -n "$pf" ] && pass "render+preflight: $name" "render: ${out:-(not a render rule)} | preflight: $pf" || fail "preflight: $name" "no finding"
    else fail "render: $name" "rendered"; fi
  done <<'EOF'
placeholder|p[PRO]['edcCallbackKey'] = 'CHANGE_ME'
mismatched EDR halves|p[PRO]['edcVault']['edrSigningPublicJwk'] = p[CON]['edcVault']['edrSigningPublicJwk']
shared custody key|p[PRO]['identityRegistryEncryptionKey'] = s['identityRegistryEncryptionKey']
svc-edc differs|p[PRO]['connectorClientSecret'] = 'a' * 64
client secret equals its id|s['svcDsPortalSecret'] = 'svc-ds-portal'
dev fixture EDR key|f = glob.glob(DS_SRC + '/services/connector/config/*-vault.properties')[0]; jwk = json.loads([l for l in open(f) if l.startswith('participant-private-key=')][0].split('=', 1)[1]); p[PRO]['edcVault']['edrSigningPrivateJwk'] = json.dumps(jwk); p[PRO]['edcVault']['edrSigningPublicJwk'] = json.dumps({k: v for k, v in jwk.items() if k != 'd'})
EOF
  # Back byte for byte (the mutations above are YAML dumps, without the file's header).
  cp "$backup" "$SECRETS"; rm -f "$t"
  cmp -s "$backup" "$SECRETS" && echo "  secrets file restored" || fail "render-negatives" "secrets file not restored"
  rm -f "$backup"
}

gate_pod_negatives() {
  local ph f
  refuses "neg connector at-rest key" "$NPRO" ds-connector-$PRO ds-connector \
    "CONNECTOR_AT_REST_KEYS holds a value that is not a Fernet key" -- --set secrets.atRestKeys=CHANGE_ME
  refuses "neg connector secrets" "$NPRO" ds-connector-$PRO ds-connector \
    "CONNECTOR_CLIENT_SECRET: |||CONNECTOR_EDC_CALLBACK_SECRET: |||CONNECTOR_KEY_INDEX_SECRET: " -- \
    --set secrets.clientSecret=CHANGE_ME --set secrets.edcCallbackKey=CHANGE_ME --set secrets.keyIndexSecret=CHANGE_ME
  refuses "neg connector db password" "$NPRO" ds-connector-$PRO ds-connector \
    "password authentication failed for user .connector_${PRO//-/_}." -- --set secrets.dbPassword=CHANGE_ME
  refuses "neg provenance pseudonym key" "$NPRO" ds-provenance-$PRO ds-provenance \
    "PROVENANCE_SUBJECT_PSEUDONYM_KEY: " -- --set secrets.subjectPseudonymKey=CHANGE_ME
  refuses "neg participant registry encryption key" "$NPRO" ds-identity-registry-$PRO ds-identity-registry \
    "IDENTITY_REGISTRY_ENCRYPTION_KEY: " -- --set secrets.identityRegistryEncryptionKey=CHANGE_ME
  refuses "neg participant registry STS secret" "$NPRO" ds-identity-registry-$PRO ds-identity-registry \
    "ir-cli: refusing to start|||IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET: " -- --set secrets.participantStsSecret=CHANGE_ME
  # ds fix 5 on the cluster: the refused rollout must not have replaced the stored hash
  # under the serving pod, so the DSO's EDC still gets STS tokens: a fresh query works.
  local out; out=$(flow flow)
  grep -q "RESULT flow PASS" <<<"$out" && pass "neg STS rollout left the serving STS intact" "full T5.3 flow after the refused rollout, no restart" \
    || fail "neg STS rollout left the serving STS intact" "$(grep -E 'catalog|RESULT' <<<"$out" | tr '\n' ' ')"
  refuses "neg anchor service client secret" "$AUTH" ds-identity-registry ds-identity-registry \
    "IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET: " -- --set secrets.serviceClientSecret=CHANGE_ME
  refuses "neg portal service client secret" "$NCON" ds-portal-$CON ds-portal \
    "PORTAL_SERVICE_CLIENT_SECRET is" -- --set secrets.portalServiceClientSecret=CHANGE_ME
  refuses "neg EDC client and control keys" "$NPRO" ds-edc-$PRO ds-edc \
    "DS_CONNECTOR_INTERNAL_CLIENT_SECRET: is a placeholder|||WEB_HTTP_CONTROL_AUTH_KEY: is a placeholder" -- \
    --set secrets.connectorClientSecret=CHANGE_ME --set secrets.edcControlApiKey=CHANGE_ME
  ph=$(mktemp); printf '%s' '{"kty":"EC","crv":"P-256","d":"CHANGE_ME","x":"CHANGE_ME","y":"CHANGE_ME"}' > "$ph"
  refuses "neg EDC vault seed placeholders" "$NPRO" ds-edc-$PRO ds-edc \
    "vault alias sts-client-secret: is a placeholder|||vault alias ds-connector-callback-key: is a placeholder|||vault alias participant-private-key: carries a placeholder private key" -- \
    --set secrets.stsClientSecret=CHANGE_ME --set secrets.edcCallbackKey=CHANGE_ME --set-file secrets.edrSigningPrivateJwk="$ph"
  rm -f "$ph"
  # A dev EDC vault under the chart's DS_ENV=production (only DS_ENV=dev relaxes the guard).
  refuses "neg dev EDC control key" "$NPRO" ds-edc-$PRO ds-edc \
    "WEB_HTTP_CONTROL_AUTH_KEY: is a committed dev default" -- --set secrets.edcControlApiKey=insecure-dev-control-key
  f=$(mktemp); grep '^participant-private-key=' "$(ls "$DS_SRC"/services/connector/config/*-vault.properties | head -1)" | cut -d= -f2- | tr -d '\n' > "$f"
  refuses "neg dev EDC vault seed" "$NPRO" ds-edc-$PRO ds-edc \
    "vault alias participant-private-key: is a committed dev fixture key|||vault alias sts-client-secret: is a committed dev default|||vault alias ds-connector-callback-key: is a committed dev default" -- \
    --set secrets.stsClientSecret=insecure-dev-secret --set secrets.edcCallbackKey=insecure-dev-callback-key --set-file secrets.edrSigningPrivateJwk="$f"
  rm -f "$f"
  # Known gap, recorded: the upstream oauth2-proxy has no guard; only the render policy
  # and the preflight stop a placeholder there.
  local before; before=$(helm history ds-oauth2-proxy-$CON -n "$NCON" -o json | jq '.[-1].revision')
  helm upgrade ds-oauth2-proxy-$CON "$CHARTS/ds-oauth2-proxy" -n "$NCON" --reuse-values --no-hooks \
    --set secrets.clientSecret=CHANGE_ME --wait=watcher --timeout 120s >/dev/null 2>&1 \
    && echo "GAP neg oauth2-proxy client secret: boots Ready on CHANGE_ME (upstream binary, no guard; render policy + preflight only)" \
    || fail "neg oauth2-proxy" "unexpected: the upgrade did not become ready"
  helm rollback ds-oauth2-proxy-$CON "$before" -n "$NCON" --no-hooks --wait=watcher --timeout 200s >/dev/null 2>&1
  # Mismatched EDR halves on the cluster: the DSO connector serves another key; a fresh
  # data plane (it caches the JWKS per process) must refuse the EDR.
  local wrong; wrong=$(mktemp); sec "p[CON]['edcVault']['edrSigningPublicJwk']" > "$wrong"
  before=$(helm history ds-connector-$PRO -n "$NPRO" -o json | jq '.[-1].revision')
  helm upgrade ds-connector-$PRO "$CHARTS/ds-connector" -n "$NPRO" --reuse-values --no-hooks \
    --set-file secrets.edrPublicJwk="$wrong" --wait=watcher --timeout 300s >/dev/null 2>&1; rm -f "$wrong"
  kubectl rollout restart -n "$DPNS" deploy/ds-data-plane >/dev/null; kubectl rollout status -n "$DPNS" deploy/ds-data-plane --timeout=180s >/dev/null
  out=$(flow query)
  grep -q "query: 401" <<<"$out" && pass "neg mismatched EDR halves (cluster)" "$(grep -o 'query: 401.*' <<<"$out" | cut -c1-80)" || fail "neg mismatched EDR halves (cluster)" "$(grep -E 'query|RESULT' <<<"$out" | tr '\n' ' ')"
  helm rollback ds-connector-$PRO "$before" -n "$NPRO" --no-hooks --wait=watcher --timeout 300s >/dev/null 2>&1
  kubectl rollout restart -n "$DPNS" deploy/ds-data-plane >/dev/null; kubectl rollout status -n "$DPNS" deploy/ds-data-plane --timeout=180s >/dev/null
  out=$(flow query); grep -q "RESULT query PASS" <<<"$out" && pass "neg mismatched halves restored" "query 200" || fail "neg mismatched halves restored" "$(grep RESULT <<<"$out")"
}

gate_rotation() {
  # Rotate the consumer's edcCallbackKey in one apply: its EDC and its connector both roll,
  # and a transfer after the roll still delivers its EDR (the callback carries the key).
  local e0 c0 e1 c1 out upd
  e0=$(newest_pod "$NCON" ds-edc-$CON); c0=$(newest_pod "$NCON" ds-connector-$CON)
  uv run -q --no-project --with pyyaml python -c "
import yaml, secrets; p = '$SECRETS'; txt = open(p).read()
head = ''.join(l for l in txt.splitlines(True)[:5] if l.startswith('#'))
d = yaml.safe_load(txt); d['secrets']['participants']['$CON']['edcCallbackKey'] = secrets.token_hex(32)
open(p, 'w').write(head + yaml.safe_dump(d, sort_keys=False))"
  upd=$(hf apply --skip-deps --suppress-diff 2>&1 | sed -n '/UPDATED RELEASES/,$p' | awk 'NR>2 {print $1}' | paste -sd' ')
  e1=$(newest_pod "$NCON" ds-edc-$CON); c1=$(newest_pod "$NCON" ds-connector-$CON)
  out=$(flow flow)
  if [ "$e1" != "$e0" ] && [ "$c1" != "$c0" ] && grep -q "RESULT flow PASS" <<<"$out"; then
    pass rotation "updated: $upd; EDC and connector rolled; a transfer after the roll delivered its EDR and queried 200"
  else fail rotation "updated: $upd; edc ${e1#pod/} connector ${c1#pod/}; $(grep RESULT <<<"$out")"; fi
}

for g in "$@"; do
  [ "$g" = all ] && set -- helm-test t2.3 t2.4 t4.1 t5.1 t5.2 t5.3 consumer-list t5.5 allowance allowance-services render-negatives pod-negatives rotation && break
done
for g in "$@"; do
  echo; echo "######## $g ($(date -u +%T)Z)"
  fn="gate_$(tr '.-' '__' <<<"$g")"
  declare -F "$fn" >/dev/null || { echo "unknown gate $g"; exit 2; }
  "$fn"
done
echo; echo "failures: $FAILS"
exit "$FAILS"
