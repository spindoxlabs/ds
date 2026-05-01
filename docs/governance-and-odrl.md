# Governance & ODRL Policy Pipeline

This document describes how datasets are declared in `governance.yaml`, converted to ODRL policies, pushed to the EDC connector, and enforced at negotiation time.

---

## Governance YAML — source of truth

Every dataset in the dataspace is declared in `services/connector/governance/governance.yaml`. The file follows the CELINE governance schema extended with `dataspace:` blocks for EDC integration.

### Structure

```yaml
defaults:
  access_level: internal
  dataspace:
    expose: false

sources:
  datasets.gold.energy_metrics:
    title: "Energy Community Metrics"
    description: "Aggregated energy consumption and production data"
    access_level: open          # open | internal | restricted | secret
    classification: green       # green | pii
    tags: [energy, metrics]
    user_filter_column: null    # set to enable consent-based row filtering

    dataspace:
      expose: true              # push to EDC catalogue
      medallion: gold           # bronze | silver | gold
      asset:
        id: "https://provider.dataspaces.localhost/assets/energy-metrics"
        content_type: application/json
      data_address:
        type: HttpData
        base_url: http://dataset-api:30002/query
        query_params:
          dataset_name: datasets.gold.energy_metrics
```

### Key fields

| Field | Purpose |
|-------|---------|
| `access_level` | Controls which ODRL constraints are generated |
| `classification` | `pii` adds consent constraints; `green` does not |
| `user_filter_column` | Column name for consent-based row filtering (e.g. `user_id`) |
| `dataspace.expose` | If `false` or `access_level: secret`, dataset is not pushed to EDC |
| `dataspace.medallion` | Data quality tier — displayed in portal UI |
| `dataspace.asset.id` | IRI used as the EDC asset ID |
| `dataspace.data_address` | Where the data lives — the EDC data plane proxies requests here |

---

## GovernanceMapper — YAML to ODRL

The `GovernanceMapper` class in `services/governance/src/ds/governance/mapper.py` converts each `GovernanceRuleV2` into three EDC payloads:

### 1. ODRL Offer (Policy)

Access level drives the constraint set:

| Access level | ODRL constraints |
|-------------|-----------------|
| `open` | No constraints. `downloadURL` included in DCAT distribution |
| `internal` | `ds:accessScope eq "dataspaces.query"` |
| `restricted` | `ds:accessScope eq "dataspaces.query"` + `ds:contractRequired eq "true"` |
| `secret` | Not exposed to EDC or the catalogue |

Additional constraints:

- When `user_filter_column` is set or `classification: pii`: adds `ds:consentStatus eq "active"`
- Tags map to `odrl:purpose` constraints via a tag-to-purpose lookup table

### 2. EDC Asset

```json
{
  "@id": "https://provider.dataspaces.localhost/assets/energy-metrics",
  "properties": {
    "name": "Energy Community Metrics",
    "contenttype": "application/json"
  },
  "dataAddress": {
    "@type": "DataAddress",
    "type": "HttpData",
    "baseUrl": "http://dataset-api:30002/query",
    "queryParams": "dataset_name=datasets.gold.energy_metrics"
  }
}
```

### 3. EDC Contract Definition

Links the asset to its policy definition, making it available for negotiation.

---

## Provider sync flow

When `POST /provider/sync` is called on ds-connector:

1. `GovernanceResolver` loads `governance.yaml` → list of `GovernanceRuleV2`
2. `GovernanceService` filters: only rules with `dataspace.expose: true` and `access_level != secret`
3. For each exposed rule, `GovernanceMapper` generates:
   - Asset creation payload → `POST /management/v3/assets`
   - Policy definition payload → `POST /management/v3/policydefinitions`
   - Contract definition payload → `POST /management/v3/contractdefinitions`
4. `ProviderService` pushes all payloads to EDC via `EdcManagementClient`
5. `ProvBridge` emits a `CataloguePublished` event to ds-provenance

---

## Policy enforcement at negotiation time

When a consumer negotiates for a dataset, EDC evaluates the ODRL constraints using custom `AtomicConstraintFunction` implementations in `edc-extensions`:

### AccessScopeFunction (`ds:accessScope`)

1. Reads `governance/participants.yaml` to find the requesting participant
2. Checks if the participant's `allowed_scopes` list contains the required scope
3. Returns `true` (allow) or `false` (deny)

### ConsentStatusFunction (`ds:consentStatus`)

1. Makes HTTP GET to `ds-connector /internal/consent/check`
2. Passes the participant DID and asset ID as query parameters
3. ds-connector queries the consent database for an active consent record
4. Returns `true` if active consent exists

### ContractRequiredFunction (`ds:contractRequired`)

Currently a pass-through (always returns `true`). Intended for bilateral contract gate enforcement.

---

## The `ds:` ODRL vocabulary

The dataspace defines custom ODRL terms under the `ds:` namespace prefix. The vocabulary is served as JSON-LD at `GET /ns/energy` on ds-connector.

| Term | Type | Values |
|------|------|--------|
| `ds:accessScope` | Constraint | `dataspaces.query`, `dataspaces.admin` |
| `ds:consentStatus` | Constraint | `active` |
| `ds:contractRequired` | Constraint | `true` |
| `ds:participantRole` | Constraint | `provider`, `consumer` |
| `ds:purpose` | Constraint | Purpose URIs mapped from tags |

---

## Participant registry

`services/connector/governance/participants.yaml` defines known dataspace participants:

```yaml
participants:
  - id: did:web:provider.dataspaces.localhost
    dsp_address: http://edc-provider:19194/protocol
    allowed_scopes: [dataspaces.query, dataspaces.admin]
    role: provider

  - id: did:web:consumer.dataspaces.localhost
    dsp_address: http://edc-consumer:29194/protocol
    allowed_scopes: [dataspaces.query]
    role: consumer
```

This file is consumed by:
- `edc-extensions/AccessScopeFunction` — participant scope validation at negotiation time
- `ds-connector/ParticipantRegistry` — catalog discovery and access control
- `ds-federated-catalog` — endpoint discovery for catalog crawling
