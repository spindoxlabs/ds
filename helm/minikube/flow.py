"""The gates' data-plane-side checks, run **inside** the data-plane stand-in pod.

`helm/minikube/gates.sh` pipes this file into `python` in the stand-in pod (the data
plane's namespace, admitted by the connectors' `ingressFrom`), preceded by two lines: the
consumer's organisation client secret and a comma-separated list of consumer
access-request ids to revoke first (an organisation token cannot list them). Nothing
secret is printed. The participants come from the environment (CONSUMER, PROVIDER,
DOMAIN, the namespaces, ASSET). MODE (env, set by the gates script):

  jwks   T5.2: `GET /internal/edr-jwks` on both connectors as `svc-ds-dataset-api`,
         and without a token.
  flow   T5.3: the ledger path ds's e2e `organisation_token` flow takes, as the consumer's
         organisation client: catalogue, negotiate, transfer, the stored EDR (which
         carries the provider's agreement id: the consumer's own does not cross), then
         `POST /query` on the stand-in, which verifies the EDR against the provider
         connector's key and asks its `/internal/dataplane/authorize`.
  query  the last step of `flow` again, on the latest started transfer.
  pep    the two PEP calls only, unauthenticated, with a short timeout: a timeout means
         the network refused them (T5.3's red case).

Each mode ends with one line `RESULT <mode> <PASS|FAIL> <detail>`.
"""

import os
import sys
import time
import urllib.parse

import httpx

KC = os.environ["DATASET_API_KEYCLOAK_TOKEN_URL"]
CON, PRO, DOMAIN = os.environ["CONSUMER"], os.environ["PROVIDER"], os.environ["DOMAIN"]
REC = f"http://ds-connector-{CON}.{os.environ['CONSUMER_NS']}.svc.cluster.local:30001"
DSO = f"http://ds-connector-{PRO}.{os.environ['PROVIDER_NS']}.svc.cluster.local:30001"
DSP = f"https://{PRO}.{DOMAIN}/protocol/2025-1"
DSO_DID = f"did:web:{PRO}.{DOMAIN}"
ASSET = os.environ.get("ASSET", "datasets.gold.grid_capacity")
MODE = os.environ.get("MODE", "flow")


def result(ok: bool, detail: str) -> None:
    print(f"RESULT {MODE} {'PASS' if ok else 'FAIL'} {detail}")
    sys.exit(0 if ok else 1)


def org_headers() -> dict:
    tok = httpx.post(KC, data={
        "grant_type": "client_credentials", "client_id": f"svc-ds-connector-{CON}",
        "client_secret": os.environ["REC_ORG_SECRET"],
        "scope": "management-api:catalog:read management-api:negotiations:write "
                 "management-api:transfers:write management-api:agreements:read"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def poll(url, headers, done, tries=60):
    body = {}
    for _ in range(tries):
        r = httpx.get(url, headers=headers, timeout=30)
        body = r.json() if r.status_code == 200 else {}
        if done(body):
            return body
        time.sleep(2)
    return body


def query(headers, transfer_id) -> httpx.Response:
    e = httpx.get(f"{REC}/consumer/edr/{urllib.parse.quote(transfer_id, safe='')}", headers=headers, timeout=30)
    if e.status_code != 200:
        result(False, f"stored EDR {e.status_code}")
    edr = e.json()
    print("edr: endpoint", edr.get("endpoint"), "| token present:", bool(edr.get("authorization")))
    return httpx.post(edr["endpoint"], json={"sql": f"SELECT * FROM {ASSET}"}, headers={
        "Authorization": edr["authorization"],
        "Edc-Contract-Agreement-Id": str(edr.get("agreement_id")),
        "Edc-Transfer-Process-Id": transfer_id}, timeout=60)


if MODE == "jwks":
    tok = httpx.post(KC, data={"grant_type": "client_credentials", "client_id": "svc-ds-dataset-api",
        "client_secret": os.environ["DATASET_API_SERVICE_CLIENT_SECRET"]}).json()["access_token"]
    out = {}
    for name, base in ((PRO, DSO), (CON, REC)):
        r = httpx.get(f"{base}/internal/edr-jwks", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        keys = r.json().get("keys", []) if r.status_code == 200 else []
        out[name] = (r.status_code, [k.get("kid") for k in keys], [k.get("x") for k in keys], any("d" in k for k in keys))
        print(name, r.status_code, "kid:", out[name][1], "x:", out[name][2], "private member:", out[name][3])
    anon = httpx.get(f"{DSO}/internal/edr-jwks", timeout=10).status_code
    print("without a token:", anon)
    expected = {p: x for p, x in (a.split("=", 1) for a in os.environ.get("EXPECT_X", "").split(",") if a)}
    ok = all(
        s == 200 and kids == ["participant-private-key"] and not d and (p not in expected or xs == [expected[p]])
        for p, (s, kids, xs, d) in out.items()
    ) and anon == 401
    result(ok, " ".join(f"{p}={v[0]}" for p, v in out.items()) + f" anonymous={anon}")

if MODE == "pep":
    outcome = []
    for path, method in (("/internal/edr-jwks", "GET"), ("/internal/dataplane/authorize", "POST")):
        try:
            r = httpx.request(method, f"{DSO}{path}", json={} if method == "POST" else None, timeout=8)
            outcome.append(f"{path}={r.status_code}")
        except httpx.TimeoutException as exc:
            outcome.append(f"{path}={type(exc).__name__}")
    print(" ".join(outcome))
    result(all("Timeout" in o for o in outcome), " ".join(outcome))

H = org_headers()

if MODE == "query":
    items = httpx.get(f"{REC}/consumer/transfers", headers=H, timeout=30).json()
    started = [t for t in items if t.get("state") == "STARTED" and t.get("asset_id") == ASSET]
    if not started:
        result(False, "no started transfer to query on")
    q = query(H, started[-1]["transfer_id"])
    print("query:", q.status_code, q.text[:160])
    result(q.status_code == 200, f"query {q.status_code} {q.text[:80]}")

# MODE == "flow"
for rid in filter(None, os.environ.get("REVOKE_IDS", "").split(",")):
    rv = httpx.post(f"{REC}/consumer/requests/{rid}/revoke", json={"reason": "gate rerun"}, headers=H, timeout=60)
    print("revoked earlier request", rid[:8], rv.status_code)
cat = httpx.post(f"{REC}/consumer/catalog", json={"counter_party_address": DSP, "counter_party_id": DSO_DID},
                 headers=H, timeout=60)
print("catalog:", cat.status_code)
if cat.status_code != 200:
    result(False, f"catalog {cat.status_code} {cat.text[:200]}")
raw = cat.json().get("dataset") or cat.json().get("dcat:dataset") or []
raw = [raw] if isinstance(raw, dict) else raw
dataset = next((d for d in raw if (d.get("@id") or d.get("id")) == ASSET), None)
if dataset is None:
    result(False, f"{ASSET} not in the provider's catalogue")
pol = dataset.get("hasPolicy") or dataset.get("odrl:hasPolicy")
pol = pol[0] if isinstance(pol, list) else pol
neg = httpx.post(f"{REC}/consumer/negotiate", json={
    "counter_party_address": DSP, "offer_id": str(pol.get("@id")), "asset_id": ASSET,
    "assigner": DSO_DID, "odrl_policy": pol,
    "declared_purpose": ["https://w3id.org/dsp/policy/purpose/GridMonitoring"],
    "justification_ref": "ds-minikube-gate"}, headers=H, timeout=60)
print("negotiate:", neg.status_code, neg.text[:200] if neg.status_code >= 300 else "")
if neg.status_code != 200:
    result(False, f"negotiate {neg.status_code}")
nid = neg.json()["negotiation_id"]
st = poll(f"{REC}/consumer/negotiations/{urllib.parse.quote(nid, safe='')}", H,
          lambda b: b.get("state") in {"FINALIZED", "VERIFIED", "AGREED", "TERMINATED"})
agreement = st.get("contractAgreementId")
print("negotiation:", st.get("state"), "| agreement id present:", bool(agreement))
if not agreement:
    result(False, f"negotiation {st.get('state')} {st.get('errorDetail') or ''}")
tr = httpx.post(f"{REC}/consumer/transfer", json={"contract_agreement_id": agreement, "counter_party_address": DSP,
    "asset_id": ASSET, "connector_id": DSO_DID}, headers=H, timeout=60)
print("transfer:", tr.status_code, tr.text[:200] if tr.status_code >= 300 else "")
if tr.status_code != 200:
    result(False, f"transfer {tr.status_code}")
tid = tr.json()["transfer_id"]
ts = poll(f"{REC}/consumer/transfers/{urllib.parse.quote(tid, safe='')}", H,
          lambda b: b.get("state") in {"STARTED", "TERMINATED"})
print("transfer state:", ts.get("state"))
q = query(H, tid)
print("query:", q.status_code, q.text[:160])
result(q.status_code == 200 and '"items"' in q.text, f"negotiation {st.get('state')}, transfer {ts.get('state')}, query {q.status_code}")
