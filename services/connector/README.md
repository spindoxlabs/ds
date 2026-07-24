# ds-connector

The EDC control-plane orchestration service. Wraps a provider-side and consumer-side Eclipse Dataspace Connector instance and exposes a unified REST API for governance sync, data flow management, consent sovereignty, and participant registry.

Port: `30001`
URL: `http://portal.dataspaces.localhost:9010/api/connector/`

---

## Purpose

EDC's Management API is low-level and stateless. This service adds:

- A governance sync layer that reads `governance.yaml` and pushes assets, policies, and contract definitions to the EDC provider
- A consumer flow abstraction that chains negotiate → poll → transfer → poll → EDR into a clean async API
- A consent registry (PostgreSQL) with subject-level granularity: create, approve, reject, revoke; revocation terminates linked EDC transfer processes
- A participant registry backed by the identity-registry service (`HttpParticipantRegistry` with TTL cache), used for access scope validation; file-based fallback available when `CONNECTOR_IDENTITY_REGISTRY_URL` is not set
- Internal endpoints consumed by the EDC policy engine (`edc-extensions`) at constraint evaluation time
- Provenance event emission to `ds-provenance` for all contract and transfer lifecycle events

---

## API groups

### Provider

- `POST /provider/sync` — reads `governance.yaml`, derives ODRL policies via `GovernanceMapper`, and pushes all exposed datasets to the EDC provider as assets + policies + contract definitions
- `GET /provider/assets` — list all assets currently registered in EDC
- `GET /provider/policies` — list all policy definitions
- `GET /provider/contracts` — list all contract definitions
- `GET /provider/transfers` — list active transfer processes on the provider side
- `GET /provider/authorizations` — returns consented subject DIDs per dataset; aggregates across all consumers, deduplicates by latest consent record; datasets without consented subjects are excluded; response contains only public identifiers (dataset IDs, subject DIDs)

### Consumer

- `POST /consumer/catalog` — fetch the provider's DCAT catalogue via DSP
- `POST /consumer/negotiate` — start a contract negotiation; returns `negotiation_id` immediately
- `GET /consumer/negotiations/{id}` — poll negotiation state
- `POST /consumer/transfer` — start a data transfer; returns `transfer_id`
- `GET /consumer/transfers/{id}` — poll transfer state
- `GET /consumer/edr/{id}` — retrieve the Endpoint Data Reference once transfer is `STARTED`
- `POST /consumer/flow` — blocking end-to-end: negotiate + transfer + EDR in a single call (for testing)

### Consent

A data *consumer* does not call these. It negotiates: a provider-side contract
negotiation for a consent-gated dataset is parked by `ConsentPendingGuard` while
the subjects decide, and the ask is recorded from EDC's DCP-verified
`counterPartyId`.

- `POST /consent/request` — **provider-local**: an operator or the portal seeds a consent request for a set of subjects. Guarded by `connector.consent.provision`
- `GET /consent/pending?correlation_id=` — is this negotiation waiting on a consent decision, and since when. Status only, for the counterparty. Guarded by `connector.consent.read`
- `GET /consent/asks` — operator view: which asks are holding up which negotiation. Guarded by `connector.provider.read`
- `POST /consent/admin/shares` — a service (onboarding) provisions a subject's standing consent from an `offer_id`; guarded by `connector.consent.provision`. Writes `consumer_id = "*"` wildcard rows with a non-PII `legal_basis` record
- `GET /consent/my` — data subject retrieves their own consent requests (requires `X-Subject-Id` header)
- `POST /consent/my/{id}/approve` — data subject approves a request; resumes the negotiation it was blocking
- `POST /consent/my/{id}/reject` — data subject rejects a request; terminates the negotiation only once every subject has refused
- `POST /consent/my/{id}/revoke` — data subject revokes a previously approved consent. Running transfers are terminated by EDC's policy monitor, not from here

### Internal (consumed by edc-extensions)

- `GET /internal/agreements/{id}/status` — check whether a contract agreement is active
- `GET /internal/consent/check` — check consent status for a (dataset, consumer) pair; returns subject IDs for row filtering
- `POST /consent/register-transfer` — link a transfer process ID to a consent record for revocation
- `GET /internal/edr-jwks` — proxy the EDC provider's JWKS endpoint for JWT verification
- `GET /internal/participants/check` — forwards scope checks to identity-registry when HTTP-backed; falls back to local file-based check otherwise

### Namespace

- `GET /ns/policy` — the profile-namespaced ODRL vocabulary as JSON-LD (`Cache-Control: public, max-age=86400`)

### Admin

- `GET /admin/participants` — list registered participants (guard `connector.admin`)
- `POST /admin/ingestion` — record a manual DSO/offline data handover (guard `connector.ingestion.record`); computes the `consent_snapshot_hash` from the consent DB and emits a `DataIngested` provenance event

Consent grants and revocations (`/consent/admin/shares`, `/consent/my/shares`, `/consent/my/{id}/approve|revoke`) emit `ConsentGranted` / `ConsentRevoked` provenance events after the write commits. All Block C events carry **codes, DIDs and hashes only, never PII**.

---

## ODRL policy derivation

The `GovernanceMapper` in `libs/governance/src/ds/governance/mapper.py` converts a `GovernanceRuleV2` into a full ODRL Offer:

- `access_level` → permitted actions (profile-namespaced actions, `odrl:aggregate`, `odrl:transfer`)
- `classification` → prohibited actions (PII datasets prohibit `odrl:distribute`, `odrl:sublicense`)
- `user_filter_column` → profile-namespaced `ConsentStatus eq "active"` constraint + `odrl:obtainConsent` pre-duty
- `policy.obligations.delete_after_days` → `odrl:delete` obligation
- `policy.obligations.attribution` → `odrl:attribute` obligation with `attributeUrl`

Tags are mapped to ODRL `odrl:purpose` via the profile's `tag_to_purpose` mapping (e.g. `meters` → `{ns}purpose:EnergyBalancing`).

---

## Governance sync

`POST /provider/sync` calls `load_exposed_datasets()` which reads `governance/governance.yaml` and returns datasets where `expose: true` and `access_level != secret`. For each dataset it creates or upserts:

1. An EDC `Asset` with a `HttpData` data address pointing to `dataset-api`
2. An EDC `PolicyDefinition` with the derived ODRL Set
3. An EDC `ContractDefinition` linking the two

The sync is idempotent — calling it multiple times is safe.

---

## Consent revocation flow

When a data subject revokes consent:

1. `revoke_consent()` fetches the `transfer_ids` linked to the consent record
2. Calls `DELETE /management/v3/transferprocesses/{id}/terminate` on the provider EDC for each active transfer
3. Sets the consent status to `revoked`

This ensures that revocation propagates to the EDC data plane within the next request cycle.

---

## Participant registry

Participants are managed by the identity-registry service and fetched via `GET /admin/participants`.

### HTTP-backed (primary — `HttpParticipantRegistry`)

The `HttpParticipantRegistry` fetches participants from the identity-registry service, configured via `CONNECTOR_IDENTITY_REGISTRY_URL`:

- Fetches from `GET {registry_url}/admin/participants` with a configurable TTL cache (default 60s via `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL`)
- On fetch error, serves stale cached data (fail-open for reads)
- `GET /internal/participants/check` forwards scope check requests to the identity-registry

### File-based (fallback)

When `CONNECTOR_IDENTITY_REGISTRY_URL` is not set, the connector falls back to reading a local YAML file via `CONNECTOR_PARTICIPANTS_REGISTRY_PATH`. This fallback exists for development or offline scenarios but is not the primary path.

---

## Configuration

All settings use the `CONNECTOR_` prefix (or `EDC_` for EDC-specific overrides):

- `CONNECTOR_PARTICIPANT_ID` — participant identifier (e.g. `provider`)
- `CONNECTOR_PARTICIPANT_BASE_URL` — base URL used as asset IRI prefix
- `CONNECTOR_PARTICIPANT_DID` — DID URI (e.g. `did:web:provider.dataspaces.localhost`)
- `EDC_PROVIDER_MANAGEMENT_URL` — provider EDC Management API URL
- `EDC_CONSUMER_MANAGEMENT_URL` — consumer EDC Management API URL
- `EDC_API_KEY` — shared API key for EDC Management API auth
- `CONNECTOR_DATABASE_URL` — PostgreSQL connection string
- `CONNECTOR_PARTICIPANTS_REGISTRY_PATH` — path to participants YAML file (file-based fallback; only used when `CONNECTOR_IDENTITY_REGISTRY_URL` is not set)
- `CONNECTOR_GOVERNANCE_YAML_PATH` — path to `governance.yaml`
- `CONNECTOR_PROVENANCE_URL` — URL of `ds-provenance` for event emission
- `CONNECTOR_IDENTITY_REGISTRY_URL` — URL of identity-registry (e.g. `http://ds-identity-registry:30005`); when unset, falls back to file-based registry
- `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL` — cache TTL in seconds for HTTP-backed participant registry (default `60`)
- `CONNECTOR_NEGOTIATION_TIMEOUT` — seconds before a negotiation poll times out
- `CONNECTOR_TRANSFER_TIMEOUT` — seconds before a transfer poll times out

---

## Development

```bash
cd services/connector
task install     # uv sync
task dev         # uvicorn with hot reload on :30001
task db:migrate  # alembic upgrade head
task test
task lint
```

To start the full connector stack (EDC instances + STS + VC wallet + db):

```bash
docker compose -f docker-compose.yml up
```

---

## Known limitations

- `POST /consumer/negotiate` and `/consumer/transfer` are thin wrappers; the main production path is `POST /consumer/flow`.
- Webhook notification URLs are validated against `CONNECTOR_WEBHOOK_ALLOWED_HOSTS` (default empty = reject all).
