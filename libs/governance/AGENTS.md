# ds-governance — Agent Guide

## Library identity

- **Role**: Shared Python library — governance YAML parsing and ODRL/EDC payload generation
- **Language**: Python 3.12
- **Type**: Library (no running service)
- **Package**: `ds-governance` (imported as `from ds.governance import ...`)

## Source layout

```
src/ds/governance/
├── __init__.py
├── models.py       GovernanceRuleV2, DataspacePolicy, DataspaceAsset, DataspaceContract Pydantic models
├── mapper.py       GovernanceMapper — converts rules to ODRL offers + EDC payloads
└── resolver.py     GovernanceResolver — loads and validates governance.yaml files
```

## Key classes

### `GovernanceRuleV2` (models.py)

The canonical Pydantic model for a single dataset entry in `governance.yaml`. Fields:

- `source_name`: dotted path (e.g. `datasets.gold.metric`)
- `title`, `description`: human-readable metadata
- `access_level`: `open | internal | restricted | secret`
- `classification`: `green | pii`
- `tags`: list of domain tags
- `user_filter_column`: column name for consent-based row filtering (optional)
- `dataspace.expose`: whether to push to EDC
- `dataspace.medallion`: `bronze | silver | gold`
- `dataspace.asset`: `id` (IRI), `content_type`
- `dataspace.data_address`: `type`, `base_url`, `query_params`

### `GovernanceMapper` (mapper.py)

Instance methods that convert a `GovernanceRuleV2` into EDC-ready payloads:

| Method | Signature | Output |
|--------|-----------|--------|
| `to_odrl_offer` | `(dataset_key, rule)` | ODRL Set with constraints based on access_level + classification + consent |
| `to_asset_create` | `(dataset_key, rule)` | EDC Asset creation payload with HttpData address |
| `to_policy_create` | `(dataset_key, rule)` | EDC PolicyDefinition creation payload |
| `to_contract_definition` | `(dataset_key, rule)` | EDC ContractDefinition creation payload |

Access level → ODRL constraint mapping:
- `open` → no constraints, `downloadURL` in DCAT
- `internal` / `restricted` → constraints driven by `access_requirements`; `partner` adds a profile-namespaced `Membership` constraint (e.g. `dsp-policy:Membership`)
- `secret` → not exposed

When `user_filter_column` is set → adds a profile-namespaced `ConsentStatus eq "active"` constraint.

### `GovernanceResolver` (resolver.py)

Loads a `governance.yaml` file and returns a list of `GovernanceRuleV2` objects. Merges `defaults` into each source entry.

## Coding conventions

- This is a pure library — no FastAPI, no database, no I/O beyond file reads
- All models are Pydantic v2 with strict validation
- ODRL output uses a configurable profile namespace for custom constraints (default prefix: `dsp-policy`)
- EDC payloads target Management API v3 format
- Changes here affect ds-connector (which imports this as an editable dependency)

## Testing

```bash
cd libs/governance
uv sync --extra dev
pytest
```

## Consumed by

- **ds-connector**: `GovernanceMapper` and `GovernanceResolver` are imported directly
- **pyproject.toml reference**: `ds-governance = { path = "../../libs/governance", editable = true }` in connector's pyproject.toml
