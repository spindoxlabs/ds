# ds-connector — Agent Guide

## Service identity

- **Role**: EDC orchestration, consent management, governance sync
- **Language**: Python 3.12, FastAPI
- **Port**: 30001 (debug: 30901)
- **URL**: `https://connector.dataspaces.localhost`
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
│   ├── edc_management.py  EdcManagementClient — typed wrapper around EDC Management API v3
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
| Change governance-to-ODRL mapping | `../governance/src/ds/governance/mapper.py` (shared lib) |
| Modify consent logic | `services/consent_service.py`, `db/models.py` |
| Change EDC API calls | `clients/edc_management.py` |
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

`governance/participants.yaml` defines known participants:

```yaml
participants:
  - id: did:web:provider.dataspaces.localhost
    dsp_address: http://edc-provider:19194/protocol
    allowed_scopes: [dataspaces.query, dataspaces.admin]
    role: provider
```

Used by `edc-extensions` `AccessScopeFunction` at negotiation time and by `ParticipantRegistry` for catalog discovery.

## Docker stack

This service's `docker-compose.yml` brings up the full connector stack:
- `edc-provider` + `edc-consumer` (Java EDC fat JARs)
- `sts-provider` + `sts-consumer` (Python STS instances)
- `vc-wallet-provider` + `vc-wallet-consumer` (Python VC wallet instances)
- `connector-db-init` (Alembic migration runner)
- `ds-connector` (this service)
- `ds-federated-catalog` (catalog crawler)

Shared infra (caddy, postgres) must be running first via root `docker compose up -d`.

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

- **Upstream**: Portal calls this service's REST API
- **Downstream**: calls EDC Management API, ds-provenance, STS, VC-wallet
- **Internal API**: EDC extensions call `/internal/*` endpoints during policy evaluation
- **Shared lib**: imports `ds-governance` (editable path dependency at `../governance`)
