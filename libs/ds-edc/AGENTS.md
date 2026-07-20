# ds-edc — Agent Guide

## Library identity

- **Role**: Shared EDC Management API v3 client and Pydantic models
- **Language**: Python 3.12
- **Import**: `import ds_edc` or `from ds_edc import EdcManagementClient`
- **No Dockerfile, no port** — consumed as an editable path dependency

## Source layout

```
src/ds_edc/
├── __init__.py      Re-exports all public symbols
├── client.py        EdcManagementClient — async httpx wrapper for EDC Management API v3
├── schemas.py       Pydantic models for EDC request/response payloads
└── webhooks.py      EDC webhook event models (transfer, negotiation)
```

## Key types

| Type | Purpose |
|------|---------|
| `EdcManagementClient` | Async httpx client wrapping all EDC v3 Management API endpoints |
| `AssetCreate` | Asset creation payload with `to_edc()` serialization |
| `PolicyCreate` | ODRL policy definition payload |
| `ContractDefCreate` | Contract definition payload |
| `CatalogRequest` | Catalog request with counter-party address |
| `NegotiationRequest` | Contract negotiation initiation |
| `NegotiationState` | Negotiation polling result |
| `TransferRequest` | Transfer process initiation |
| `TransferState` | Transfer polling result |
| `EdrResponse` | Endpoint Data Reference (auth token + endpoint) |
| `TransferProcessEvent` | EDC transfer webhook event |
| `ContractNegotiationEvent` | EDC negotiation webhook event |

## Consumers

- `services/connector` — primary consumer (re-exports via shim modules for back-compat)
- `libs/ds-e2e` — e2e test framework (depends on ds-edc for shared constants)

## Coding conventions

- Pure Pydantic models + httpx — no FastAPI, no SQLAlchemy
- All HTTP calls are async via `httpx.AsyncClient`
- EDC JSON-LD context: `{"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}`
- Protocol version: `dataspace-protocol-http:2025-1`
- Authentication via `X-Api-Key` header

## Adding to a service

In the service's `pyproject.toml`:

```toml
[project]
dependencies = ["ds-edc"]

[tool.uv.sources]
ds-edc = { path = "../../libs/ds-edc", editable = true }
```

In `Dockerfile`, add `COPY libs/ds-edc/ /build/ds-edc/` and install it.
