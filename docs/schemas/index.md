# Schemas

ds ingests governance authored in repos it does not control — a pipeline repository
writes `governance.yaml`, `sharing-offers.yaml` and `vocabularies.yaml`, and a
connector reads them at sync time. These schemas let the authoring side validate
**before** ds ever sees the file, instead of discovering a problem when a sync
refuses it.

Every document below is served from this site at a stable address. That address is
also the schema's own `$id`, so pointing an editor or a CI step at it needs nothing
but the URL.

## Published documents

| Schema | Validates | Defined by |
|---|---|---|
| [`sharing-offers.schema.json`](sharing-offers.schema.json) | `sharing-offers.yaml` — the offers declared alongside a governance file | ds (`SharingOffer`) |
| [`vocabularies.schema.json`](vocabularies.schema.json) | `vocabularies.yaml` — semantic vocabularies served from `/ns/{slug}`, matched to a dataset by `dcat.conforms_to` | ds (`Vocabulary`) |
| [`odrl-profile.schema.json`](odrl-profile.schema.json) | an ODRL profile — the purpose taxonomy and namespace a deployment enforces against | ds (`OdrlProfile`) |
| [`purpose-vocabulary.json`](purpose-vocabulary.json) | a single `dataspace.purpose` entry — see below, this one is not a JSON Schema for a file | ds (the active ODRL profile) |
| [`governance.schema.json`](governance.schema.json) | `governance.yaml` | [celine-utils](https://celine-eu.github.io/schema/governance.schema.json) |

Stable URLs, for `$schema` keys, `yaml-language-server` comments and CI:

```
https://spindoxlabs.github.io/ds/schemas/sharing-offers.schema.json
https://spindoxlabs.github.io/ds/schemas/vocabularies.schema.json
https://spindoxlabs.github.io/ds/schemas/odrl-profile.schema.json
https://spindoxlabs.github.io/ds/schemas/purpose-vocabulary.json
https://spindoxlabs.github.io/ds/schemas/governance.schema.json
```

In an editor, one comment on line 1 of the file is enough:

```yaml
# yaml-language-server: $schema=https://spindoxlabs.github.io/ds/schemas/sharing-offers.schema.json
sharing_offers:
  - id: ...
```

## The rule: a schema lives where the shape is defined

`governance.yaml` is the only shape celine-utils defines; everything else here, ds
defines. That rule is what makes the split legible rather than arbitrary, and it is
the answer to "why is one of these read-only in the repo": `governance.schema.json`
is a cached copy of the upstream document, kept in-tree so the conformance test
runs offline in CI. The rest are generated from the Pydantic models in
`ds-governance` — the models are the definition, and a schema maintained by hand
beside a live model drifts until both look authoritative.

Regeneration and refresh are developer workflows, documented in
[`schemas/README.md`](https://github.com/spindoxlabs/ds/blob/main/schemas/README.md).
A test regenerates and diffs, so drift fails CI rather than surfacing as a producer
being told their valid file is wrong.

## `purpose-vocabulary.json` is not a JSON Schema

It is the list of purpose slugs the **active profile** accepts, plus each one's
label, definition, hierarchy and DPV alignment. No static governance schema can
carry this: the taxonomy is deployment configuration, so the permitted values are
only knowable from the profile in force. A producer validates a `dataspace.purpose`
entry against the `enum` in that document rather than finding out at sync.

`GET /ns/policy` on a running connector serves the same taxonomy with its full SKOS
structure. Both are built from the profile, so they cannot disagree — but the
published file is a snapshot of *this* repo's profile, and a deployment that
overlays its own taxonomy is authoritative over it. The alignment behind each
entry's `dpv` IRI is documented in [DPV 2.3](../taxonomies/dpv-2.3.md).

## Not covered

`owners.yaml`, participants, `catalogues.yaml`, `clients.yaml`, `organizations.yaml`
and `agreements.dev.yaml`. Their Pydantic models are the de-facto definitions and no
external repo authors them against a published contract today. They get published
here when one does.

See also [ds-governance](../services/libs/governance.md) for the models behind these
documents, and [Data models](../rulebook/data-models.md) for what the dataspace has
decided they must express.
