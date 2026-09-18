{{/*
The publishing step, as a script rather than as a shell pipeline.

`httpx` is already in the connector image (`libs/ds-edc` depends on it), so this
needs no second image and no `curl`. Written here rather than inline in the Job so
the quoting is in one place and the logic is readable.

Three things it does that a `curl … && echo ok` would not:

* **it reads `errors`, not the status code.** The route answered `200` while every
  dataset failed, in a live deployment, for a fortnight;
* **it reports what changed**, `withdrawn` included — a sync that takes a dataset
  off offer is an event an operator should see in the job's log;
* **it fails when the provider published nothing**, because a provider whose
  governance is mounted and whose catalogue is empty is broken, not idle.
*/}}
{{- define "conn.syncScript" -}}
import json, os, sys, time
import httpx

token_url = os.environ["SYNC_TOKEN_URL"]
base = os.environ["SYNC_CONNECTOR_URL"].rstrip("/")
timeout = float(os.environ.get("SYNC_TIMEOUT", "60"))

# The connector is ready by hook order, but a rollout is not an instant, so the
# first call is retried rather than treated as a verdict.
deadline = time.monotonic() + timeout
last = None
while time.monotonic() < deadline:
    try:
        httpx.get(f"{base}/health", timeout=10).raise_for_status()
        break
    except Exception as exc:
        last = exc
        time.sleep(2)
else:
    sys.exit(f"connector never became healthy at {base}: {last}")

token = httpx.post(
    token_url,
    data={
        "grant_type": "client_credentials",
        "client_id": os.environ["SYNC_CLIENT_ID"],
        "client_secret": os.environ["SYNC_CLIENT_SECRET"],
    },
    timeout=30,
)
token.raise_for_status()
access = token.json()["access_token"]

r = httpx.post(
    f"{base}/provider/sync",
    json={},
    headers={"Authorization": f"Bearer {access}"},
    timeout=300,
)
try:
    body = r.json()
except ValueError:
    sys.exit(f"provider sync answered {r.status_code} with a non-JSON body: {r.text[:500]}")

print(json.dumps(body, indent=2))
if body.get("errors"):
    sys.exit(f"provider sync reported {len(body['errors'])} error(s); nothing is published that this names")
if not body.get("synced"):
    sys.exit("provider sync published no dataset — governance is mounted and the catalogue is empty")
print(f"published {len(body['synced'])}, withdrew {len(body.get('withdrawn') or [])}")
{{- end -}}
