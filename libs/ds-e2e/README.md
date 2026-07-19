# ds-e2e

End-to-end verification framework for the dataspaces platform. Exercises the full consumer-pull DSP flow against a running stack and reports step-by-step results.

## Install

```bash
cd libs/ds-e2e
uv sync
```

## Usage

```bash
# Check all services are reachable
ds-e2e health

# Run the full smoke flow (catalog → negotiate → transfer → query → revoke)
ds-e2e run --flow smoke

# Run with cleanup first (idempotent start)
ds-e2e run --flow smoke --clean-first

# Run a specific use-case flow
ds-e2e run --flow uc1    # delegated consent / subject-pool
ds-e2e run --flow uc2    # owner-scoped negotiation
ds-e2e run --flow uc3    # open/external data

# Run all flows
ds-e2e run --flow all

# Reset runtime state (truncate connector/provenance tables + re-sync)
ds-e2e clean

# Output formats
ds-e2e run --format json
ds-e2e run --format markdown
```

## Taskfile integration

From repo root:

```bash
task e2e           # smoke flow
task e2e:health    # service reachability
task e2e:clean     # reset state
task e2e:all       # all flows with cleanup
task e2e:uc1       # UC-1
task e2e:uc2       # UC-2
task e2e:uc3       # UC-3
```

## Configuration

Settings are loaded from `.env.local` (repo root) via pydantic-settings. Key variables:

| Env var | Default | Purpose |
|---------|---------|---------|
| `CONNECTOR_URL` | `http://172.17.0.1:30001` | Provider connector |
| `CATALOG_CONNECTOR_URL` | `http://172.17.0.1:31001` | Consumer connector |
| `CONNECTOR_DATASET_API_URL` | `http://172.17.0.1:30002` | Dataset API |
| `CONNECTOR_PROVENANCE_URL_PROVIDER` | `http://172.17.0.1:30000` | Provenance |
| `CONNECTOR_IDENTITY_REGISTRY_URL` | `http://172.17.0.1:30005` | Identity registry |
| `E2E_COUNTER_PARTY_ADDRESS` | `http://edc-provider:19194/protocol/2025-1` | DSP counter-party (Docker DNS) |
| `KEYCLOAK_TOKEN_URL` | `http://localhost:9080/realms/.../token` | Service token endpoint |
| `SVC_DS_PORTAL_ID` / `SECRET` | `svc-ds-portal` | Service client credentials |
| `SMOKE_DATABASE_URL` | `postgresql://postgres:postgres@172.17.0.1:35432` | DB for cleanup |

## Adding a new flow

1. Create `src/ds_e2e/flows/my_flow.py`:

```python
from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

class MyFlow(BaseFlow):
    name = "my-flow"
    description = "What this flow verifies"

    def execute(self) -> FlowResult:
        result = FlowResult(flow_name=self.name)
        # Use self.settings for config, self.http for requests
        try:
            data = self.http.get(f"{self.settings.connector_url}/some/endpoint")
            result.pass_step("step name", "detail")
        except Exception as exc:
            result.fail_step("step name", str(exc))
        return result
```

2. Register in `src/ds_e2e/flows/__init__.py`:

```python
from ds_e2e.flows.my_flow import MyFlow
FLOW_REGISTRY["my-flow"] = MyFlow
```

3. Add the flow name to the `FlowName` enum in `cli.py`.

## Architecture

```
cli.py          → Typer commands (run, clean, health)
config.py       → E2ESettings (pydantic-settings, reads .env.local)
http.py         → HttpClient (httpx sync, polling, service token)
models.py       → Step, FlowResult (structured results)
cleanup.py      → DB truncation + provider re-sync
runner.py       → Orchestrates flow execution
flows/base.py   → BaseFlow ABC
flows/smoke.py  → Full DSP consumer-pull flow
flows/uc1.py    → Subject-pool validation
flows/uc2.py    → Owner-scoped negotiation
flows/uc3.py    → Open/external data
```
