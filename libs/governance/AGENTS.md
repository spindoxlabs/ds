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
├── models.py       GovernanceRuleV2, DataspacePolicy, OdrlProfile, PurposeConcept, DpvMapping
├── sharing.py      SharingOffer, OfferRecipients, user_visible_hash — the consent vocabulary
├── mapper.py       GovernanceMapper — converts rules to ODRL offers + EDC payloads
├── resolver.py     GovernanceResolver — loads and validates governance.yaml files
├── owners.py       OwnersRegistry / HttpOwnersRegistry — owner alias resolution
├── matrix.py       Explainable policy matrix for the portal
├── cli.py          `ds-governance` — the pre-import validation gate
├── profiles/
│   └── energy.yaml Shipped ODRL profile: namespace, operands, purpose taxonomy
└── compliance/
    ├── checks.py         Governance checks (ids, owners, retention, data address)
    ├── consent_checks.py Consent-vocabulary checks (purposes, offers, controllers)
    ├── validator.py      validate() — runs both check families
    ├── runtime.py        Live identity-registry lookups
    └── evidence.py       DCAT-AP catalog + ODRL offers as audit artifacts
```

## Key classes

### `GovernanceRuleV2` (models.py)

The canonical Pydantic model for a single dataset entry in `governance.yaml`. Fields:

- `source_name`: dotted path (e.g. `datasets.gold.metric`)
- `title`, `description`: human-readable metadata
- `access_level`: `open | internal | restricted | secret`
- `classification`: `green | pii`
- `tags`: DCAT-AP catalogue keywords — **no policy meaning** (see below)
- `policy.purpose`: the purposes this dataset may serve — the only runtime source
- `policy.consent.required`: gate rows on subject consent
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

> **`resolve()` falls back to `defaults` for an unknown key.** That is right for
> catalogue rendering and wrong for a consent write, where an unvalidated key would
> be silently accepted. Callers that need strictness must test membership in
> `config.sources` first — the connector does this in
> `services/consent_vocabulary.py::resolve_dataset`.

## The consent vocabulary

### Purposes are declared, never derived from tags

`policy.purpose[]` is the **only** runtime source of a dataset's purposes.
`OdrlProfile.tag_to_purpose` survives solely as an authoring default when
scaffolding a new entry (`GovernanceMapper.derive_purposes_from_tags`).

A tag is a *topic*; a purpose is a *reason for processing*. One meter dataset can
serve incentive calculation, flexibility research or cost optimisation, so deriving
one from the other is a category error — and `tags` is overloaded anyway
(`[meters, silver, pii, rec]` mixes domain, medallion layer, sensitivity and community).

The mapper emits **one** `odrl:purpose` constraint per permission (`isA` for a single
purpose, `isAnyOf` for several). Constraints inside a permission are ANDed, so one
per purpose would demand a consumer's use serve all of them at once.

### `PurposeConcept` — two fields, two jobs

| Field | Served at `/ns/policy` as | Used for |
|---|---|---|
| `broader` | `skos:broader` | **Enforcement.** `OdrlProfile.is_a()` walks this chain and nothing else |
| `dpv_mapping` | the declared `skos:*Match` | **Interop/docs only.** Never matched against |

> Following a `broadMatch` during enforcement would let a consumer whose policy names
> a generic DPV term satisfy a member's specific consent. `is_a()` is deliberately
> written so this is impossible; `test_is_a_never_follows_dpv_mapping` pins it.

`OdrlProfile` helpers: `purpose_index`, `purpose_slug()` (normalises slug / full IRI /
compact form, returns `None` for anything unknown — never a wildcard),
`broader_chain()` (terminates on cycles), `is_a(requested, consented)`.

### `SharingOffer` (sharing.py)

What a person is actually asked: a purpose-scoped bundle, from a named controller,
for a described category of recipient. Loaded by `load_sharing_offers(path, overlay_name)`,
which merges `sharing-offers.<overlay>.yaml` by offer id.

`user_visible_hash()` is the re-consent trigger — SHA-256 over the facts the person
read. It **excludes `datasets[]` by design**: which datasets back an offer is a
schema-migration concern nobody was shown, so changing them must not invalidate
consent. It reacts to purpose (and its broader chain), legal basis, controller,
controller role, processor category, subject scope, measures, resolution, coverage,
retention and revocability.

## The validation gate — `ds-governance`

`validate()` runs two check families. Consent checks activate when a
`sharing_offers_path` is given; the CLI picks up `sharing-offers.yaml` next to the
governance file by convention, or takes `--sharing-offers`.

```bash
task compliance:validate           # offline, against the YAML seeds
task compliance:validate:runtime   # against a running identity-registry
task compliance:evidence           # DCAT-AP catalog + ODRL offers
```

Controller-role validation needs owner alias → DID → participant roles, joined by
`build_role_lookup()`. When no owners registry is available the controller check
downgrades to a warning rather than blocking an offline run — `RoleLookup.available`
distinguishes "nothing to check against" from "the registry has no such controller".

## Coding conventions

- This is a pure library — no FastAPI, no database, no I/O beyond file reads
- All models are Pydantic v2 with strict validation
- ODRL output uses a configurable profile namespace for custom constraints (default prefix: `dsp-policy`)
- EDC payloads target Management API v3 format
- **Keep the schema domain-neutral.** The energy profile is one shipped, overridable
  instance; nothing in `models.py` or `sharing.py` may assume energy concepts
- Changes here affect ds-connector (which imports this as an editable dependency)

## Testing

```bash
cd libs/governance
uv sync --extra dev
pytest
```

| File | Covers |
|---|---|
| `test_models.py` | Rule and profile parsing, profile loading and overrides |
| `test_mapper.py` | ODRL offers and EDC payloads, purpose declaration and dedup |
| `test_sharing.py` | Purpose hierarchy, `is_a` semantics, offer schema, `user_visible_hash` |
| `test_compliance_checks.py` | Governance gate |
| `test_consent_checks.py` | Consent-vocabulary gate |

## Consumed by

- **ds-connector**: `GovernanceMapper`, `GovernanceResolver`, `OdrlProfile` and
  `load_sharing_offers` are imported directly
- **pyproject.toml reference**: `ds-governance = { path = "../../libs/governance", editable = true }` in connector's pyproject.toml
