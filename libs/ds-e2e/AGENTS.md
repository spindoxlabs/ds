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
    ├── __init__.py        Flow registry
    ├── base.py            BaseFlow ABC
    ├── smoke.py           Full DSP consumer-pull flow
    ├── consent_purpose.py Consent vocabulary: taxonomy, offers, purpose enforcement
    ├── uc1.py             Subject-pool validation
    ├── uc2.py             Owner-scoped negotiation
    └── uc3.py             Open/external data
```

## Flows

| Flow | Needs the EDC? | Covers |
|---|---|---|
| `smoke` | yes | Catalogue → negotiate → transfer → query → revoke, with an offer-based consent grant. Asserts a query for an unconsented purpose **and** a query with no purpose both return zero rows |
| `consent-purpose` | **no** | SKOS taxonomy at `/ns/policy`, the `/ns/sharing-offers` projection, `422` on invalid consent writes, offer expansion, and the full `odrl:isA` matrix at `/internal/consent/check` |
| `uc1` / `uc2` / `uc3` | yes | Governance patterns GP-1 / GP-2 / GP-3 |

`consent-purpose` needs only ds-connector, identity-registry and Keycloak, so it is the
fastest way to verify the consent vocabulary when the EDC is unavailable.

The consent vocabulary the flows assert against is pinned in `config.py`
(`sharing_offer_id`, `consented_purpose`, `unconsented_purpose`) and must stay in step
with `services/connector/governance/sharing-offers.yaml` and the ODRL profile. The
negative purpose is deliberately one the *dataset* permits but the *subject* never
agreed to — that is the case that proves the purpose chain is enforced rather than
merely declared.

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
