# ds-e2e — Agent Guide

End-to-end verification framework for the dataspaces platform.

## Source layout

```
src/ds_e2e/
├── cli.py          Typer CLI (run, clean, health)
├── config.py       E2ESettings — pydantic-settings, reads .env.local
├── http.py         HttpClient — sync httpx, polling, service token caching
├── models.py       Step, FlowResult
├── runner.py       Flow orchestration
├── cleanup.py      DB truncation + EDC state reset + provider sync
└── flows/
    ├── __init__.py Flow registry
    ├── base.py     BaseFlow ABC
    ├── smoke.py    Full DSP consumer-pull flow
    ├── uc1.py      Subject-pool validation
    ├── uc2.py      Owner-scoped negotiation
    └── uc3.py      Open/external data
```

## Key design

- **Sync httpx** — no async needed for a sequential CLI runner
- **pydantic-settings** — reads `.env.local` from repo root (same env vars as services)
- **Modular flows** — each flow is a `BaseFlow` subclass registered in `FLOW_REGISTRY`
- **Idempotent cleanup** — truncates connector/provenance tables, terminates EDC negotiations/transfers, deletes EDC objects, re-syncs provider
- **`E2E_COUNTER_PARTY_ADDRESS`** — must match the participant registry's DSP address (Docker DNS: `http://edc-provider:19194/protocol/2025-1`)

## Adding a flow

1. Create `flows/my_flow.py` with a `BaseFlow` subclass implementing `execute() -> FlowResult`
2. Register in `flows/__init__.py`
3. Add to `FlowName` enum in `cli.py`

## Known gaps

- Post-revoke query enforcement: the dataset-api-mock (provider-side) doesn't see consumer-side revocations because the provider EDC has different agreement/transfer IDs than the consumer
- UC1/UC2 membership check: `svc-ds-portal` may lack the scope for the identity-registry `/memberships/check` endpoint
