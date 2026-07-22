# ds-governance

Shared Python library used by `ds-connector`. Contains the `GovernanceRuleV2` Pydantic model, the `GovernanceMapper` that converts rules into ODRL and EDC Management API payloads, the `GovernanceResolver` that reads and merges `governance.yaml` files, and the `ds-governance` CLI for offline validation.

Not a running service — imported as a library.

---

## Purpose

`governance.yaml` files live in data pipeline repositories (in project-specific pipeline repositories). The same file is read by two consumers:

- Pipeline-side `GovernanceResolver` — for OpenLineage facet injection
- `ds-connector` via this library — EDC side, for ODRL policy and asset creation

This library provides the EDC side of that shared contract. It is fully backward-compatible with `GovernanceRule` v1 — files that don't use `dcat:` or `dataspace:` blocks load without errors.

---

## Models (`models.py`)

`GovernanceRuleV2` extends `GovernanceRule` (v1) with:

- `DataspacePolicy` — permitted/prohibited actions, purpose, validity dates, obligations, audience, and consent requirements
- `DataspaceAsset` — asset ID and content type for EDC
- `DataspaceDataAddress` — HTTP data address for the EDC data plane proxy
- `DataspaceContract` — policy and contract definition IDs for EDC
- `DataspaceConfig` — the `dataspace:` block: `contract_required`, `consent_required`, `odrl_action`, `purpose`, `medallion`, `asset`, `data_address`, `contract`

`DcatConfig` and `DataspaceConfig` are parsed from the YAML but `DcatConfig` is primarily consumed by dataset-api, not by this library.

### OdrlProfile

`OdrlProfile` defines the ODRL vocabulary configuration used by `GovernanceMapper`:

| Field | Description |
|-------|-------------|
| `namespace` | Base namespace URI (default: `https://w3id.org/dsp/policy/`) |
| `prefix` | Short prefix for the namespace (e.g. `dsp`) |
| `membership_operand` | Left-operand name for membership constraint (default: `Membership`) |
| `consent_operand` | Left-operand name for consent constraint (default: `ConsentStatus`) |
| `purposes` | Purpose taxonomy — list of purpose terms available in the vocabulary |
| `tag_to_purpose` | Mapping from dataset tags to purpose URIs (e.g. `meters` → `{ns}purpose:EnergyBalancing`) |

`load_odrl_profile(path)` loads an `OdrlProfile` from a YAML file. When no path is given, it defaults to the bundled `profiles/energy.yaml`.

---

## ODRL mapper (`mapper.py`)

`GovernanceMapper` converts a `GovernanceRuleV2` into ODRL and EDC Management API payloads.

Inputs:
- `profile: OdrlProfile` — defines the ODRL namespace, purpose taxonomy, and tag-to-purpose mapping
- `participant_id` — used as the `odrl:assigner` DID fragment (e.g. `provider` → `did:web:provider.dataspaces.localhost`)
- `base_url` — base URL for asset IRI generation
- `owner_did_resolver: Callable[[str], str | None]` (optional) — resolves dataset owners for attribution duties

Key methods:

`to_odrl_offer(dataset_key, rule)` — returns a full ODRL Offer dict:

- `access_level` → permitted actions (`open`: query + aggregate + transfer; `internal`: query + aggregate; `restricted`: query only)
- `access_requirements` → membership/contract constraints (`all`: none; `partner`: `{ns}Membership`; `contract`: `{ns}Membership` + `{ns}ContractRequired`)
- `classification` → prohibited actions (PII datasets prohibit transfer, derive, distribute, sublicense)
- `user_filter_column` or `consent.required` → `{ns}ConsentStatus eq active` constraint + `odrl:obtainConsent` pre-duty
- Tags → `odrl:purpose` via `profile.tag_to_purpose` (e.g. `meters` → `{ns}purpose:EnergyBalancing`)
- `obligations.delete_after_days` → `odrl:delete` obligation with `odrl:delayPeriod` refinement (`odrl:lteq`)
- `obligations.attribution` → `odrl:attributeTo` duty

All constraint values use `@id` wrapping for consistent JSON-LD serialization. The namespace prefix and all term IRIs are derived from the loaded `OdrlProfile`.

`to_asset_create(dataset_key, rule)` — returns an EDC Asset with `HttpData` data address pointing to dataset-api, plus namespace-prefixed property annotations (`medallion`, `classification`, `userFilterColumn`, `tags`).

`to_policy_create(dataset_key, rule)` — returns an EDC `PolicyDefinition` wrapping the ODRL Offer as an ODRL Set.

`to_contract_definition(dataset_key, rule, policy_id, asset_id)` — returns an EDC `ContractDefinition` linking the policy and asset.

---

## Resolver (`resolver.py`)

`GovernanceResolver` wraps the upstream `GovernanceResolver` with `GovernanceRuleV2` output. Reads a `governance.yaml` file and resolves per-source rules by merging defaults.

```python
resolver = GovernanceResolver.from_file(Path("governance/governance.yaml"))
rule = resolver.resolve("datasets.gold.meters_15m")
```

`load_exposed_datasets(path)` in `ds-connector/services/governance.py` uses this to return only datasets where `expose: True` and `access_level != "secret"`.

---

## DS namespace

The ODRL extension vocabulary is hosted at `GET /ns/policy` by `ds-connector`, generated dynamically from the active `OdrlProfile`. The namespace URI is configurable via the profile (default: `https://w3id.org/dsp/policy/`).

Custom terms:
- `{ns}Membership` — left-operand: participant membership check
- `{ns}ConsentStatus` — left-operand: active consent check
- `{ns}purpose:{PurposeName}` — purpose values derived from `OdrlProfile.purposes` (e.g. `{ns}purpose:EnergyBalancing`)
- `{ns}role:DataSubject` — consent pre-duty role
