# ds-governance

`import ds.governance`

The library that turns a **governance declaration into an enforceable policy**. It is the
single place where a line in a YAML file becomes an ODRL constraint the EDC will evaluate.

It parses `governance.yaml` and `sharing-offers.yaml` into typed models, resolves the rule that
applies to a dataset key, converts that rule into an ODRL Offer and the three EDC payloads
(asset, policy definition, contract definition), validates a governance file before it can be
imported, emits DCAT-AP and ODRL audit evidence, and generates the JSON Schemas this repository
publishes.

[`services/connector`](../connector.md) is its principal in-repo importer;
[`services/dataset-api-mock`](../dataset-api-mock.md) imports it for the
[data-plane decision contract](#the-data-plane-decision-contract) alone.

## Role in the blueprint

| | |
|---|---|
| Implements | [DSSC · Access & Usage Policies Enforcement](../../blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) · [DSSC · Data, Services & Offerings Descriptions](../../blueprints/dssc/data-value-creation-enablers/data-services-and-offerings-descriptions.md) · [DSSC · Data Models](../../blueprints/dssc/data-interoperability/data-models.md) |
| Rules it enforces | [Rulebook · Policies](../../rulebook/policies.md) · [Rulebook · Catalogue and metadata](../../rulebook/catalogue-and-metadata.md) · [Rulebook · Data models](../../rulebook/data-models.md) |

## The shape of a governance file

```yaml
defaults:
  access_level: internal

sources:
  datasets.silver.meters_15m:
    title: 15-minute meter readings
    ownership: [{name: example-org}]
    access_level: restricted
    classification: pii
    retention_days: 365
    row_filters:
      - handler: rec_registry
        args: {column: device_id}
    policy:
      purpose: [EnergyCommunityOperation, IncentiveCalculation, FlexibilityResearch]
      consent:
        required: true
    dataspace:
      expose: true
      sharing_offers: [household-energy-flexibility]
```

Three blocks matter:

| Block | Decides |
|---|---|
| top level | *what the dataset is* — title, ownership, access level, classification, retention, row filters, tags |
| `policy:` | *how it may be used* — purposes, permitted and prohibited actions, obligations, consent |
| `dataspace:` | *how it is published* — exposure, medallion, asset id, data address, contract ids, which sharing offers cover it |

A dataset points at its offers; an offer never lists its datasets.

## How a rule is resolved

1. Parse the base file and, if an overlay is named, `governance.<overlay>.yaml` beside it.
2. Merge the two, then merge `defaults` under the matched source.
3. Match the dataset key exactly; failing that, take the **longest** matching glob; failing
   that, `defaults` alone.

**The merge is not simply "override wins."** Three fields are deliberately monotonic:

| Field | Rule | Why |
|---|---|---|
| `policy.purpose` | **union** | an overlay adds a reason for processing; it does not retract one |
| `policy.consent.required` | **OR** | once consent is required, a layer on top cannot un-require it |
| `policy.obligations.contract_required` | **OR** | same |
| `tags` | union | |
| everything else | field-wise override; `None` preserves the base | |

A consequence worth knowing: an overlay **cannot un-expose** a dataset by setting
`dataspace.expose: false`, because `false` is the default and defaults are excluded from the
merge. Use `access_level: secret` instead — which produces an offer with zero permissions.

## The ODRL a rule becomes

One permission per permitted action, all carrying the same constraint list (constraints inside
a permission are ANDed).

**Permitted actions**, unless `policy.permitted_actions` overrides them:

| `access_level` | Actions |
|---|---|
| `open` | query, aggregate, transfer |
| `internal` (also the default) | query, aggregate |
| `restricted` | query |
| `secret` | *none* — the offer carries no permission at all |

**Prohibitions**, unless `policy.prohibited_actions` overrides them:

| `classification` | Prohibited |
|---|---|
| `pii` | transfer, derive, distribute, sublicense |
| `red` | transfer, sublicense |
| `yellow` | sublicense |
| `green` (also the default) | *none* |

**Constraints**, in this order:

| Emitted when | Left operand | Right operand |
|---|---|---|
| access requires partner/contract, or the level is internal or restricted | `{ns}Membership` | `owner:<alias>:member`, `owner:<alias>:partner`, or the audience scope |
| access requires a contract | `odrl:industry` | `contract-agreed` |
| level is restricted, or `contract_required` | `ds:contractRequired` | `true` |
| exactly one purpose resolves | `odrl:purpose` `isA` | the purpose IRI |
| two or more purposes resolve | `odrl:purpose` `isAnyOf` | one flat array of IRIs |
| consent required, or a row filter exists | `{ns}ConsentStatus` | `active` |

The last condition also attaches an `odrl:obtainConsent` duty.

!!! note "Why `isAnyOf` and not several constraints"
    Constraints within a permission are ANDed, so one constraint per purpose would demand a
    consumer's use serve *all* of them at once. An `odrl:or` of scalar `isA` was tried against
    EDC and fails JSON-LD compaction. The flat multi-valued array is the shape that survives.

## Purposes are a taxonomy, not a list

The ODRL profile (`libs/governance/src/ds/governance/profiles/energy.yaml` by default) declares the purpose vocabulary: a slug, a
label, a definition, an optional `broader` parent, and an optional DPV alignment.

The bundled energy profile has nine concepts, five of them roots:

```
EnergyCommunityOperation ── IncentiveCalculation
                         ├─ CostOptimization
                         └─ FlexibilityResearch
GridMonitoring
GridResilience
EnergyForecasting
EnergyPlanning ────────── PVPotentialAssessment
```

**`broader` is the only thing purpose matching follows.** Consent to a root covers a narrower
request; the reverse never holds; siblings never match each other.

**`dpv_mapping` is recorded for readers and never consulted by matching.** That is deliberate:
a `broadMatch` to a generic DPV term would let an unrelated use satisfy a specific consent.

A purpose that is neither a known slug nor an absolute IRI is **dropped silently** during
mapping — which is why the validator exists, and why the connector refuses to sync a dataset
whose purposes do not resolve.

## Sharing offers

A sharing offer is what a data subject is actually shown: a purpose, a legal basis, a
controller and their role, a processor category, a subject scope, safeguard measures, a
resolution, a coverage window and a retention period.

Two composition rules, and they differ on purpose:

- **Contributions** (`sharing-offers.d/*.yaml`) are a **union**. A duplicate id across two
  contributing files is an error naming both — with no privileged baseline there is no winner
  to pick.
- **Overlays** (`sharing-offers.<name>.yaml`) are applied last and **replace** by offer id.

### `controller_roles` — the unbundling vocabulary

An offer's `recipients.controller_role` names *which function* of a legal entity is the
controller. The file declares the vocabulary it uses, beside the offers:

```yaml
controller_roles:
  grid-operator: [metering, operations]
```

A controller absent from the map is not unbundled, and an offer naming it may not carry a
`controller_role`. A controller present in it **is**, so an offer naming it must say which
function — matching on the legal entity alone is what [Personal data](../../rulebook/personal-data.md)
`D-11` calls insufficient. Both directions are errors at the gate.

**This is not the identity-registry's participant `roles`.** Those are DSP capacities, which
the registry pins to `{provider, consumer}`, so no `controller_role` could ever be one of
them. The check compared the two until 2026-08-08 and was therefore unsatisfiable: it could
only pass by comparing against an empty set, which is what it did against every registry.
Declaring the vocabulary here also makes the check **offline** — a producer's own file answers
it, so no registry is needed.

Composition follows the same split as the offers, except that an *identical* redeclaration is
accepted: two contributing files unbundling the same controller **differently** is an error
naming both, and an overlay may rebind it.

Each offer carries a `user_visible_hash` over the facts a person actually saw — purpose and its
broader chain, legal basis, controller and role, processor category, subject scope, measures,
resolution, coverage, retention, revocability. It deliberately excludes the backing datasets
and the text version. **A changed hash under an unchanged text version is what triggers
re-consent.**

## Validation

`ds-governance validate` runs the checks below before a governance file may be imported.
Errors block; warnings do not.

| Group | Checks |
|---|---|
| File | exists, parses, declares sources, exposes something |
| Enums | access level, classification |
| Collisions | two dataset keys deriving the same asset, policy or contract id |
| Coherence | consent required with no filter; `pii` with no filter; a blank filter column |
| Bounds | retention and delete-after ≤ 0; `valid_from` after `valid_until` |
| Owners | ownership declared, alias resolvable, the owner's DID a registered participant |
| Purposes | IRI shape, hierarchy cycles, DPV relation validity, labels, and that every dataset's purposes resolve |
| Offers | purpose in the taxonomy, no duplicate ids, every named offer resolvable, `pii` datasets declaring an offer must require consent, the offer's purpose must be in the dataset's, controller resolvable and its `controller_role` one the file [declares](#controller_roles-the-unbundling-vocabulary), legal basis a DPV term, ISO-8601 durations, and hash stability |

## Configuration

The library reads no settings of its own — the connector passes everything explicitly. Four
environment variables exist as fallbacks for external users of the library:

| Variable | Meaning |
|---|---|
| `GOVERNANCE_OVERLAY_NAME` | overlay name when the caller passes none |
| `SHARING_OFFERS_OVERLAY_NAME` | the same, for offers |
| `GOVERNANCE_CONFIG_PATH` | explicit governance file for auto-discovery |
| `PIPELINES_ROOT` | root under which auto-discovery looks for `apps/<app>/governance.yaml` |

### ODRL profile fields

| Field | Default | Emitted as |
|---|---|---|
| `namespace` | `https://w3id.org/dsp/policy/` | base of every profile IRI |
| `prefix` | `dsp-policy` | the `@context` key, and the asset-property prefix |
| `membership_operand` | `Membership` | the membership constraint's left operand |
| `consent_operand` | `ConsentStatus` | the consent constraint's left operand |
| `query_action` | `Query` | the `{query}` action placeholder |
| `purpose_base` | `purpose/` | the path segment between namespace and slug |
| `profile_iri` | — | added to `@context` as `odrl:profile` when set |
| `purposes` | `[]` | the taxonomy |

## CLI

```sh
ds-governance validate  --file governance.yaml [--owners …] [--profile …] [--format text|json|markdown] [--strict]
ds-governance evidence  --file governance.yaml --out-dir reports/compliance --name core
ds-governance collect-offers 'apps/**/sharing-offers.yaml' --out-dir …
```

`validate` exits non-zero on any error (and, with `--strict`, on any warning). `evidence`
writes a DCAT-AP catalogue and an ODRL offer graph alongside a human-readable report, and exits
non-zero if it checked nothing.

| Task | Runs |
|---|---|
| `task compliance:validate` | validate the connector's governance against the seeded owners |
| `task compliance:validate:runtime` | the same, resolving owners against a running identity registry |
| `task compliance:evidence` | write the evidence artefacts |
| `task -d libs/governance schema:generate` | regenerate the published JSON Schemas |
| `task -d libs/governance schema:refresh` | re-fetch the externally-defined governance schema |

## The data-plane decision contract

`ds.governance.dataplane` holds the shape of `POST /internal/dataplane/authorize` — the
connector's answer to a data-plane PEP. It lives here rather than in the connector because it
has readers the connector does not ship with: the celine `dataset-api` in a deployment,
`services/dataset-api-mock` in a local run.

| Model | Carries |
|---|---|
| `DataplaneDecision` | the envelope — `decision`, `reason`, `agreement_id`, `transfer_id`, `purpose`, `datasets[]`, `cache` |
| `DatasetVerdict` | one dataset's answer, because a single SQL statement can touch several and the envelope is the strictest of them |
| `DataplaneRowFilter` | `handler`, `args`, `principals` |

Two properties are the point of it:

**The row filter travels whole.** Handler, args and principals — never a column and a list of
ids. The handler is what knows how a person maps to values in the column: `rec_registry`
resolves a member to their devices, `direct_user_match` matches the subject directly. `args`
is opaque to the PDP, so a handler's own arguments reach it intact.

**Unknown fields are refused** (`extra="forbid"`). The dangerous drift is one-way — a PDP that
adds a narrowing an older PEP ignores serves rows it should have withheld. A parse failure is
a denial, which is the side [rulebook `CR-4`](../../rulebook/policies.md) chooses. The cost is
accepted: upgrading the connector ahead of a PEP stops the data plane rather than widening it.

A PEP that cannot apply a filter it was given has **not** been permitted to serve unfiltered
rows. An *allow* carrying a filter says *these rows*.

## Published schemas

The repository publishes the shapes it *defines* under `schemas/`:

| File | Origin |
|---|---|
| `sharing-offers.schema.json` | generated from the `SharingOffer` model |
| `odrl-profile.schema.json` | generated from the `OdrlProfile` model |
| `purpose-vocabulary.json` | generated from the active profile |
| `governance.schema.json` | **cached**, not generated — defined outside this repository |
