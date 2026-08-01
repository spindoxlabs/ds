# `schemas/` — the YAML shapes this repo publishes

ds ingests governance authored in repos it does not control. These schemas let
that authoring side validate **before** ds ever sees the file, instead of
discovering a problem when a sync refuses it.

> **These files are published.** The docs site serves each one at the address it
> declares as its own `$id` — <https://spindoxlabs.github.io/ds/schemas/> — so a
> producer points `$schema` at the URL and never vendors a copy. The reference
> page is <https://spindoxlabs.github.io/ds/schemas/>; this README covers the
> local workflow, i.e. how these files are regenerated and refreshed.

## The rule: a schema lives where the shape is defined

| File | Defined by | Status here |
|---|---|---|
| `sharing-offers.schema.json` | **ds** (`SharingOffer`) | generated — do not edit |
| `vocabularies.schema.json` | **ds** (`Vocabulary`) | generated — do not edit |
| `odrl-profile.schema.json` | **ds** (`OdrlProfile`) | generated — do not edit |
| `purpose-vocabulary.json` | **ds** (the active ODRL profile) | generated — do not edit |
| `governance.schema.json` | **celine-utils** | **cache** — do not edit |

That rule is what makes the cache/generated split legible rather than arbitrary,
and it is the answer to "why is one of these read-only". `governance.yaml` is the
only shape celine-utils defines; everything else here, ds defines.

## Generated, not written

The Pydantic models are the definition. A schema maintained by hand beside a live
model drifts, and then both look authoritative — the schema rejects files the
platform accepts, or accepts files it refuses.

```bash
task -d libs/governance schema:generate
```

`libs/governance/tests/tests/test_schema_export.py` regenerates and diffs, so
drift fails CI rather than surfacing as a producer being told their valid file is
wrong.

### `purpose-vocabulary.json` is not a JSON Schema

It is the list of purpose slugs the **active profile** accepts, plus each one's
label, definition, hierarchy and DPV alignment. No static governance schema can
carry this: the taxonomy is deployment configuration, so the permitted values are
only knowable from the profile in force. A producer validates a
`dataspace.purpose` entry against `enum` here rather than finding out at sync.

`GET /ns/policy` serves the same taxonomy at runtime with its full SKOS
structure. Both are built from the profile, so they cannot disagree —
**regenerate this file whenever the profile changes.** The alignment behind each
entry's `dpv` IRI is documented in `docs/taxonomies/dpv-2.3.md`.

## The cached one

`governance.schema.json` is a copy of
<https://celine-eu.github.io/schema/governance.schema.json>, not a fork and not a
second definition. Changing that shape means changing it in celine-utils and
refreshing here:

```bash
task -d libs/governance schema:refresh
```

A copy exists because the conformance test
(`libs/governance/tests/tests/test_schema_conformance.py`) has to run in CI and
offline. A test that fetches over the network either fails when the network is
down — noise — or skips, which enforces nothing at exactly the moment it matters.

## Not covered

`owners.yaml`, participants, `catalogues.yaml`, `clients.yaml`,
`organizations.yaml` and `agreements.dev.yaml`. Their Pydantic models are the
de-facto definitions and no external repo authors them against a published
contract today. Add them here when one does.
