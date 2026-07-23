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
│   ├── consumer.py      POST /consumer/catalog, POST /consumer/{negotiate,transfer,flow}, GET /consumer/{negotiations,transfers,edr}/*
│   ├── consent.py       POST /consent/request, GET/POST /consent/my/shares, POST /consent/my/{id}/{approve,reject,revoke}
│   ├── history.py       GET /history/{negotiations,agreements,transfers} — paginated EDC state queries
│   ├── internal.py      GET /internal/agreements/*/status, GET /internal/consent/check, POST /consent/register-transfer, GET /internal/edr-jwks
│   └── namespace.py     GET /ns/policy, GET /ns/sharing-offers — public vocabularies
├── services/
│   ├── governance.py    GovernanceService — loads governance.yaml, filters by expose flag
│   ├── consent_vocabulary.py Resolution + matching for datasets, purposes and offers
│   ├── circle.py        Who is a covered processor vs an independent controller
│   ├── provider_service.py   ProviderService — sync assets/policies/contracts to EDC
│   ├── consumer_service.py   ConsumerService — negotiate/transfer/poll/edr
│   ├── consent_service.py    ConsentService — CRUD + revocation → transfer termination
│   ├── agreement_service.py  AgreementService — EDC contract agreement queries
│   └── prov_bridge.py        ProvBridge — emit provenance events to ds-provenance
├── clients/
│   ├── edc_management.py  Re-exports EdcManagementClient from shared libs/ds-edc
│   └── provenance.py     ProvenanceClient — POST events to ds-provenance
├── registry/
│   └── participants.py   HttpParticipantRegistry — fetches participants from identity-registry API with TTL cache; file-based fallback when identity_registry_url is empty
├── notifications/
│   ├── base.py           Notifier protocol
│   ├── smtp.py           SMTP email notifier
│   ├── webhook.py        Webhook notifier
│   └── null.py           No-op notifier (default)
└── db/
    ├── engine.py         async engine + session factory
    └── models.py         ContractAgreementORM, ConsentRequestORM, ConsumerTransferORM, ConsumerAccessRequestORM
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Add a new API endpoint | `api/v1/<group>.py`, register router in `main.py` |
| Change governance-to-ODRL mapping | `../../libs/governance/src/ds/governance/mapper.py` (shared lib) |
| Modify consent logic | `services/consent_service.py`, `db/models.py` |
| Add a purpose, or change purpose matching | `../../libs/governance/.../profiles/energy.yaml`, `services/consent_vocabulary.py` |
| Add or change a sharing offer | `governance/sharing-offers.yaml`, then `task compliance:validate` |
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
    tags: [energy, metrics]        # DCAT-AP keywords — no policy meaning
    policy:
      purpose: [EnergyCommunityOperation]   # the ONLY runtime purpose source
      consent:
        required: true             # gate rows on subject consent
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

`ConnectorGovernanceMapper._to_edc_constraint` renders purpose IRIs as plain strings
for the EDC policy while the public ODRL offer keeps `{"@id": <iri>}`. EDC compares
right operands as literals, and `ConsentStatusFunction` reads the negotiated purposes
back out of the permission — it needs a string to find.

## Sharing offers — `governance/sharing-offers.yaml`

What a person is actually asked to consent to: a purpose-scoped bundle, from a named
controller, for a described category of recipient. Same overlay mechanism as
`governance.yaml` (`sharing-offers.<name>.yaml`; `*.local.yaml` is gitignored).

Served publicly at `GET /ns/sharing-offers` as **codes plus an English fallback**, so
a frontend composes its own sentences per locale and can never invent a resolution or
widen a coverage window. Dataset keys are not in the public projection.

`legal_basis` decides the UI: only `dpv:Consent` offers get a control. Contract-based
processing is disclosed, not toggled — `POST /consent/my/shares` returns **409** for a
non-consent-based offer, so a UI bug cannot manufacture a choice that does not exist.

## The consent vocabulary — where writes are validated

`services/consent_vocabulary.py` is the single place the three vocabularies meet.
Every consent write resolves through it:

| Function | Guarantees |
|---|---|
| `resolve_dataset` | The key is declared in governance — not merely resolvable via `defaults` |
| `normalise_purposes` | Every purpose exists in the taxonomy; stored as slugs. Raises rather than dropping |
| `purpose_covered` | `odrl:isA` over the local `broader` chain only |
| `resolve_offer` / `public_offer_projection` | Offer lookup and the public codes-only shape |

`VocabularyError` surfaces as **422** at the API boundary. Configuration is cached per
process (`lru_cache`); call `reset_caches()` after a governance reload or in tests.

### Enforcement rules that are easy to get wrong

- **Empty `purpose[]` is never a wildcard for personal data.** For a consent-required
  dataset it means the person was never told the use, so the row fails closed.
- **An absent requested purpose also fails closed.** A PEP that predates the purpose
  chain receives zero rows, not all of them.
- **An unknown `dataset_id` reaching `/internal/consent/check` is treated as
  consent-required**, so a mis-keyed request denies rather than leaks.
- **Consent to a child purpose does not cover its parent** — that would widen consent.

### The circle (`services/circle.py`)

Decides whether a requester is a *covered processor* (disclose, never ask) or an
*independent controller* (ask). `admitted_by` constraints are ANDed, an empty list
admits nobody, and an unknown constraint kind is unsatisfiable.

Capacity comes from the participant's current accepted agreement. Until the
identity-registry exposes agreements, capacity is unprovable and everyone resolves to
*outside the circle* — which asks rather than assumes. A redundant question is
recoverable; a skipped one is not.

## Participant registry

Participants are registered in the identity-registry service and discovered via `GET /admin/participants`. The `ParticipantRegistry` class (`registry/participants.py`) implements an `HttpParticipantRegistry` that fetches participants from identity-registry with a TTL cache.

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

`tests/conftest.py` points the consent vocabulary at `tests/fixtures/` before any
settings are read, so the suite asserts against a stable vocabulary rather than the
dev catalogue, and clears the vocabulary caches per test. `tests/__init__.py` provides
`make_headers` (service token), `make_user_headers` (user groups) and `make_vc_headers`
(the `X-Subject-Id` + `X-User-VC` mechanism the `/consent/*` routes actually use).

> Three tests fail on `main` for reasons unrelated to consent
> (`test_internal_wrong_scope_returns_403`, `test_webhook_wrong_scope_returns_403`,
> `test_asset_create_basic`). Treat that as the baseline, not as regressions.

## Integration points

- **Upstream**: Portal calls this service's REST API (JWT-authenticated via `svc-ds-portal` service account)
- **Downstream**: calls EDC Management API, ds-provenance, identity-registry (`/participants` for registry, `/users/resolve` for user lookup)
- **Internal API**: EDC extensions and dataset-api call `/internal/*` endpoints during policy evaluation (JWT-authenticated via `svc-edc` / `svc-ds-dataset-api` service accounts)
- **Shared libs**: imports `ds-governance` (governance rules/ODRL), `ds-auth` (JWT auth), `ds-edc` (EDC client + schemas) — all editable path dependencies under `../../libs/`
