# ds-governance

Shared Python library used by `ds-connector` and `edc-extensions`. Contains the `GovernanceRuleV2` Pydantic model, the `GovernanceMapper` that converts rules into ODRL and EDC Management API payloads, and the `GovernanceResolver` that reads and merges `governance.yaml` files.

Not a running service — imported as a library.

---

## Purpose

`governance.yaml` files live in data pipeline repositories (in project-specific pipeline repositories). The same file is read by two consumers:

- legacy pipeline `GovernanceResolver` — pipeline side, for OpenLineage facet injection
- `ds-connector` via this library — EDC side, for ODRL policy and asset creation

This library provides the EDC side of that shared contract. It is fully backward-compatible with legacy `GovernanceRule` v1 — files that don't use `dcat:` or `dataspace:` blocks load without errors.

---

## Models (`models.py`)

`GovernanceRuleV2` extends `GovernanceRule` (v1) with:

- `DataspacePolicy` — permitted/prohibited actions, purpose, validity dates, obligations, audience, and consent requirements
- `DataspaceAsset` — asset ID and content type for EDC
- `DataspaceDataAddress` — HTTP data address for the EDC data plane proxy
- `DataspaceContract` — policy and contract definition IDs for EDC
- `DataspaceConfig` — the `dataspace:` block: `contract_required`, `consent_required`, `odrl_action`, `purpose`, `medallion`, `asset`, `data_address`, `contract`

`DcatConfig` and `DataspaceConfig` are parsed from the YAML but `DcatConfig` is primarily consumed by dataset-api, not by this library.

---

## ODRL mapper (`mapper.py`)

`GovernanceMapper` converts a `GovernanceRuleV2` into ODRL and EDC Management API payloads.

Inputs:
- `participant_id` — used as the `odrl:assigner` DID fragment (e.g. `provider` → `did:web:provider.dataspaces.localhost`)
- `base_url` — base URL for asset IRI generation

Key methods:

`to_odrl_offer(dataset_key, rule)` — returns a full ODRL Offer dict:

- `access_level` → permitted actions (`open`: query + aggregate + transfer; `internal`: query + aggregate; `restricted`: query only)
- `classification` → prohibited actions (PII datasets prohibit transfer, derive, distribute, sublicense)
- `user_filter_column` or `consent.required` → `ds:consentStatus eq active` constraint + `odrl:obtainConsent` pre-duty
- Tags → `odrl:purpose` via `_TAG_TO_PURPOSE` (e.g. `meters` → `ds:purpose:EnergyBalancing`)
- `obligations.delete_after_days` → `odrl:delete` obligation
- `obligations.attribution` → `odrl:attribute` obligation

`to_asset_create(dataset_key, rule)` — returns an EDC Asset with `HttpData` data address pointing to dataset-api, plus `ds:` property annotations (`medallion`, `classification`, `userFilterColumn`, `tags`).

`to_policy_create(dataset_key, rule)` — returns an EDC `PolicyDefinition` wrapping the ODRL Offer as an ODRL Set.

`to_contract_definition(dataset_key, rule, policy_id, asset_id)` — returns an EDC `ContractDefinition` linking the policy and asset.

---

## Resolver (`resolver.py`)

`GovernanceResolver` wraps legacy pipeline `GovernanceResolver` with `GovernanceRuleV2` output. Reads a `governance.yaml` file and resolves per-source rules by merging defaults.

```python
resolver = GovernanceResolver.from_file(Path("governance/governance.yaml"))
rule = resolver.resolve("datasets.gold.meters_15m")
```

`load_exposed_datasets(path)` in `ds-connector/services/governance.py` uses this to return only datasets where `expose: True` and `access_level != "secret"`.

---

## DS namespace

The `ds:` ODRL extension vocabulary is hosted at `GET /ns/energy` by `ds-connector`. The namespace URI is `https://dataspaces.localhost/ns/energy#`.

Custom terms:
- `ds:accessScope` — left-operand: participant scope check
- `ds:consentStatus` — left-operand: active consent check
- `ds:contractRequired` — left-operand: bilateral contract gate
- `ds:purpose:EnergyBalancing`, `ds:purpose:GridMonitoring`, etc. — purpose values
- `ds:role:DataSubject` — consent pre-duty role
