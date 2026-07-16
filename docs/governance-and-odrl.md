# Governance & ODRL Policy Pipeline

This document describes how datasets are declared in `governance.yaml`, converted to ODRL policies, pushed to the EDC connector, and enforced at negotiation time.

---

## Governance YAML — source of truth

Every dataset in the dataspace is declared in `services/connector/governance/governance.yaml`. The file follows the governance schema extended with `dataspace:` blocks for EDC integration.

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

The `GovernanceMapper` class in `libs/governance/src/ds/governance/mapper.py` converts each `GovernanceRuleV2` into three EDC payloads. It accepts an `OdrlProfile` (loaded via `load_odrl_profile()`) that defines the ODRL namespace, purpose taxonomy, and tag-to-purpose mapping. An optional `owner_did_resolver: Callable[[str], str | None]` resolves dataset owners for attribution duties.

### 1. ODRL Offer (Policy)

Access level determines which actions are permitted, while the `access_requirements` field drives membership and contract constraints:

| Access level | ODRL constraints |
|-------------|-----------------|
| `open` | No constraints. `downloadURL` included in DCAT distribution |
| `internal` / `restricted` | Driven by `access_requirements` (see below) |
| `secret` | Not exposed to EDC or the catalogue |

The `access_requirements` field controls additional constraints:

| `access_requirements` | Constraints added |
|-----------------------|-------------------|
| `all` | No extra constraint |
| `partner` | `{ns}Membership` |
| `contract` | `{ns}Membership` + `{ns}ContractRequired` |

Where `{ns}` is the namespace from the loaded `OdrlProfile` (default `https://w3id.org/dsp/policy/`).

Additional constraints:

- When `user_filter_column` is set or `classification: pii`: adds `{ns}ConsentStatus eq "active"`
- Tags map to `odrl:purpose` constraints via the profile's `tag_to_purpose` mapping (e.g. `meters` → `{ns}purpose:EnergyBalancing`)

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
2. `OdrlProfile` is loaded via `load_odrl_profile()` (defaults to bundled `profiles/energy.yaml`)
3. `GovernanceService` filters: only rules with `dataspace.expose: true` and `access_level != secret`
4. For each exposed rule, `GovernanceMapper` (initialized with the loaded `OdrlProfile`) generates:
   - Asset creation payload → `POST /management/v3/assets`
   - Policy definition payload → `POST /management/v3/policydefinitions`
   - Contract definition payload → `POST /management/v3/contractdefinitions`
5. `ProviderService` pushes all payloads to EDC via `EdcManagementClient`
6. `ProvBridge` emits a `CataloguePublished` event to ds-provenance

---

## Policy enforcement at negotiation time

When a consumer negotiates for a dataset, EDC evaluates the ODRL constraints using custom `AtomicConstraintFunction` implementations in `edc-extensions`:

### AccessScopeFunction (`{ns}Membership`)

1. Reads `governance/participants.yaml` to find the requesting participant (file-based fallback)
2. When `CONNECTOR_IDENTITY_REGISTRY_URL` is set, scope checks are forwarded to the identity-registry HTTP endpoint (with TTL cache) instead
3. Checks if the participant satisfies the required membership constraint
4. Returns `true` (allow) or `false` (deny)

### ConsentStatusFunction (`{ns}ConsentStatus`)

1. Makes HTTP GET to `ds-connector /internal/consent/check`
2. Passes the participant DID and asset ID as query parameters
3. ds-connector queries the consent database for an active consent record
4. Returns `true` if active consent exists

---

## The dataspace ODRL vocabulary

The dataspace defines custom ODRL terms under a configurable namespace prefix. The namespace is defined by the loaded `OdrlProfile` (default: `https://w3id.org/dsp/policy/`). The vocabulary is served as JSON-LD at `GET /ns/policy` on ds-connector, generated dynamically from the active profile.

| Term | Type | Description |
|------|------|-------------|
| `{ns}Membership` | Constraint | Membership check for the requesting participant |
| `{ns}ConsentStatus` | Constraint | Active consent check (`active`) |
| `{ns}purpose:{PurposeName}` | Constraint | Purpose URIs derived from `OdrlProfile.tag_to_purpose` (e.g. `{ns}purpose:EnergyBalancing`) |

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

When `CONNECTOR_IDENTITY_REGISTRY_URL` is set, the HTTP-backed identity-registry (with TTL cache) replaces the file-based `participants.yaml` for participant lookups. File-based mode is preserved as a fallback when the environment variable is not configured.

This file is consumed by:
- `edc-extensions/AccessScopeFunction` — participant scope validation at negotiation time (file-based fallback)
- `ds-connector/ParticipantRegistry` — catalog discovery and access control
- `ds-federated-catalog` — endpoint discovery for catalog crawling
