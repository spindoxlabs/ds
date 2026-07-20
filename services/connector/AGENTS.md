# ds-connector — Agent Guide

## Service identity

- **Role**: EDC orchestration, consent management, governance sync
- **Language**: Python 3.12, FastAPI
- **Port**: 30001 (debug: 30901)
- **URL**: `http://portal.dataspaces.localhost:9010/api/connector/` (via Caddy), direct `http://172.17.0.1:30001`
- **Database**: PostgreSQL (`connector` DB), async SQLAlchemy + Alembic

## Source layout

```
src/connector/
├── main.py              FastAPI app factory with lifespan hooks
├── config.py            Pydantic settings (ConnectorSettings)
├── api/v1/
│   ├── provider.py      POST /provider/sync, GET /provider/{assets,policies,contracts,transfers}
│   ├── consumer.py      GET /consumer/catalog, POST /consumer/{negotiate,transfer,flow}, GET /consumer/{negotiations,transfers,edr}/*
│   ├── consent.py       POST /consent/request, GET /consent/my, POST /consent/my/{id}/{approve,reject,revoke}
│   ├── history.py       GET /history/{negotiations,agreements,transfers} — paginated EDC state queries
│   ├── internal.py      GET /internal/agreements/*/status, GET /internal/consent/check, POST /internal/consent/register-transfer, GET /internal/edr-jwks
│   └── namespace.py     GET /ns/energy — ds: ODRL vocabulary JSON-LD
├── services/
│   ├── governance.py    GovernanceService — loads governance.yaml, filters by expose flag
│   ├── provider_service.py   ProviderService — sync assets/policies/contracts to EDC
│   ├── consumer_service.py   ConsumerService — negotiate/transfer/poll/edr
│   ├── consent_service.py    ConsentService — CRUD + revocation → transfer termination
│   ├── agreement_service.py  AgreementService — EDC contract agreement queries
│   └── prov_bridge.py        ProvBridge — emit provenance events to ds-provenance
├── clients/
│   ├── edc_management.py  Re-exports EdcManagementClient from shared libs/ds-edc
│   └── provenance.py     ProvenanceClient — POST events to ds-provenance
├── registry/
│   └── participants.py   ParticipantRegistry — loads participants.yaml
├── notifications/
│   ├── base.py           Notifier protocol
│   ├── smtp.py           SMTP email notifier
│   ├── webhook.py        Webhook notifier
│   └── null.py           No-op notifier (default)
└── db/
    ├── engine.py         async engine + session factory
    └── models.py         ConsentRecord, TransferTracking ORM models
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new API endpoint | `api/v1/<group>.py`, register router in `main.py` |
| Change governance-to-ODRL mapping | `../../libs/governance/src/ds/governance/mapper.py` (shared lib) |
| Modify consent logic | `services/consent_service.py`, `db/models.py` |
| Change EDC API calls | `../../libs/ds-edc/src/ds_edc/client.py` (shared lib) |
| Add a new provenance event | `services/prov_bridge.py`, `clients/provenance.py` |
| Add/change config settings | `config.py` (Pydantic settings with env vars) |
| Database schema change | `db/models.py` → run `task db:revision MESSAGE=description` |

## Coding conventions

- All database access is async (`async with session` pattern)
- Use `httpx.AsyncClient` for HTTP calls, never `requests`
- EDC Management API calls go through `EdcManagementClient` — never call EDC directly from routes
- Settings loaded from env vars with sensible local-dev defaults — no `.env` file required
- Route handlers are thin: validate input, call service, return response
- Use `tenacity` for retry logic on EDC polling
- Import the governance library as `from ds.governance.mapper import GovernanceMapper`

## Governance YAML

The governance source of truth is `governance/governance.yaml`. Structure:

```yaml
defaults:
  access_level: internal
  dataspace:
    expose: false

sources:
  datasets.gold.metric:
    title: "Energy Metrics"
    access_level: open|internal|restricted|secret
    classification: green|pii
    tags: [energy, metrics]
    dataspace:
      expose: true
      medallion: gold|silver|bronze
      asset:
        id: "https://..."
        content_type: application/json
      data_address:
        type: HttpData
        base_url: http://dataset-api:30002/query
```

The `GovernanceMapper` converts this to ODRL offers + EDC payloads. `secret` datasets are never exposed.

## Participant registry

Participants are registered in the identity-registry service and discovered via `GET /participants`. The `ParticipantRegistry` class (`registry/participants.py`) implements an `HttpParticipantRegistry` that fetches participants from identity-registry with a TTL cache.

Used by `edc-extensions` `AccessScopeFunction` at negotiation time and by the federated catalog for provider discovery.

## Docker stack

This service runs as part of the provider (`docker-compose.provider.yml`) or consumer (`docker-compose.consumer.yml`) stacks:
- `edc-provider` / `edc-consumer` (Java EDC fat JARs)
- `ds-connector-provider` / `ds-connector-consumer` (this service)
- `ds-provenance-provider` / `ds-provenance-consumer`
- `dataset-api-provider` (provider only)
- `ds-federated-catalog-provider` (provider only)
- DB init containers (create DB + Alembic migrations)

Shared infra (caddy, postgres, identity-registry, keycloak) must be running first via `task infra:start`.

## Testing

```bash
task setup          # install deps
task run            # dev server with hot-reload
task db:migrate     # apply migrations
pytest              # run tests
ruff check src/     # lint
```

Tests use `pytest-asyncio` and `respx` for HTTP mocking. Test database is SQLite (in-memory).

## Integration points

- **Upstream**: Portal calls this service's REST API (JWT-authenticated via `svc-ds-portal` service account)
- **Downstream**: calls EDC Management API, ds-provenance, identity-registry (`/participants` for registry, `/users/resolve` for user lookup)
- **Internal API**: EDC extensions and dataset-api call `/internal/*` endpoints during policy evaluation (JWT-authenticated via `svc-edc` / `svc-ds-dataset-api` service accounts)
- **Shared libs**: imports `ds-governance` (governance rules/ODRL), `ds-auth` (JWT auth), `ds-edc` (EDC client + schemas) — all editable path dependencies under `../../libs/`
