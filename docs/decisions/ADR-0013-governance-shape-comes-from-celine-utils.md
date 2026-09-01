# ADR-0013 — The governance shape comes from `celine.governance`

**Date:** 2026-08-31
**Status:** accepted

## Context

`governance.yaml` is a shape ds does not define. `celine-utils` defines it, publishes
`governance.schema.json`, and ds caches that schema under `schemas/` precisely so the two
cannot drift — *a schema lives where the shape is defined*.

The code that **reads** the shape did not follow the same rule. `libs/governance` carries its
own models, resolver, overlay merge, owner registry and access-level vocabulary — a parallel
implementation of what `celine.governance` now ships. This was not an oversight, and the
reason is recorded on the celine side, in `celine-utils/.github/workflows/governance-thin.yaml`:

> `celine.governance` exists because `celine-utils` used to require dbt, Meltano, Prefect and
> Keycloak in order to parse a YAML file — so `dataset-api`, `ds` and `celine-superset` each
> wrote their own parser rather than take that dependency, and the four then disagreed about
> what the same file meant.

**That blocker is gone.** The package's core is `pydantic`, `pyyaml` and `jsonschema`, it
supports Python 3.10 upward, it is published to PyPI, and a dedicated CI job installs it with
no extras and imports `celine.governance` so that a regained dependency fails there rather
than at a downstream consumer's install. The thin core exists for consumers like this one.

What the parallel implementation costs is not hypothetical. ds's models are a **subset** of
the canonical schema, and pydantic drops what a model does not declare, so a field ds does
not know about loses its meaning rather than being carried:

- **`expose`.** The canonical schema has two exposure gates combined as AND — `expose` gates
  the catalogue and the query API, `dataspace.expose` gates the dataspace offer. ds models
  only the second. The first lands in `extra` and is read by nothing, so `expose: false` with
  `dataspace.expose: true` — which `celine.governance.exposure.exposure_conflict` names as a
  contradiction — validates PASS here, the connector publishes the asset, a consumer
  negotiates and **concludes a contract**, and the transfer then fails at a data plane that
  was never going to serve it ([#20](https://github.com/spindoxlabs/ds/issues/20)).
- **`ontology`.** celine merges it as a whole replacement because its two fields are
  alternatives; ds has no field, so it is dict-merged per key and can produce a rule
  declaring both. Latent only because ds reads it nowhere.

The merge semantics agree today — tags union, ownership and row-filters replaced when
non-empty, purpose union, `consent_required`/`contract_required` OR, `expose` deliberately not
OR. They agree by parallel maintenance rather than by construction, and ds's own docstring
names its reference as `dataset-api`'s `_merge_dataspace` — a *third* copy. Three
implementations kept in step by hand is the state the celine work set out to end.

## Decision

**`celine.governance` is the reference implementation of the governance shape, and ds imports
it rather than restating it.**

`celine-utils` becomes a runtime dependency of `libs/governance`. The division follows the
rule the schema cache already follows — *the shape lives where it is defined, the use lives
where it is used*:

| Comes from `celine.governance` | Stays in `ds.governance` |
|---|---|
| `GovernanceRule`, `GovernanceConfig`, `DataspaceConfig`, `DcatConfig`, `OntologyConfig`, `GovernanceOwner` | the ODRL mapper and profile, sharing offers, the purpose taxonomy, the vocabulary registry and cache, the compliance checks, the data-plane contract |
| `parse_rule`, `GovernanceResolver`, `from_file_with_override` | `DataspaceSpec` and `GovernanceRuleV2`, as **subclasses** — the EDC concerns (`asset`, `data_address`, `contract`, `sharing_offers`) and ds's `policy` view |
| `merge_configs`, `merge_rules`, `merge_dataspace`, `merge_models` | the ds-only fields those merges must carry |
| `effective_expose`, `dataspace_expose`, `exposure_conflict` | when a conflict is reported, and what refuses on it |
| `levels`, `owners`, `validation` | the owner *resolution* ds performs against a live registry |

The subclass shape is not ds's invention: `DataspaceConfig`'s own docstring says the EDC
sub-objects "are `ds`'s concern and are carried in its own `DataspaceSpec` subclass", and
`GovernanceRule`'s says "`ds` extends this". Both models are `extra="ignore"`, so a file may
carry ds's fields without celine's model rejecting it.

**This adds a code dependency to an integration point that was data-only, so it is a change to
the platform boundary.** `knowledge/publishing-boundary.md` lists *Governance schemas* as one
of five points and requires a decision before a sixth. This is that decision, and it does not
open a sixth point — it deepens the third from a cached artifact to a shared library, which is
the same relationship expressed more strongly.

## Consequences

**Independence was a stance, not a requirement.** ds stays adoptable: `celine.governance` is a
public PyPI package with three dependencies, no celine deployment assumptions, and a CI job
that exists to keep it that way. An adopter installs a YAML parser, not a platform.

**Divergence becomes impossible rather than detectable.** A field ds does not model is carried
by celine's model instead of being dropped, and a merge rule changes in one place.

**#20 dissolves rather than being fixed.** `expose` is `Optional[bool]` upstream with a
documented fallback to `dataspace.expose`, so adopting the model gives ds the tri-state and
`exposure_conflict` gives it the check. Closing #20 by hand would be a fourth implementation
of a rule that already exists.

**The upstream shape may move.** `celine.governance` is expected to become its own
distribution; the import path changes when it does, and `governance-thin` exists so that stays
a rename.

**What this does not decide.** Whether ds's `policy` view survives as a separate structure or
collapses into celine's `DataspaceConfig` is an implementation question for the migration, not
a boundary question. Neither is whether the cached `schemas/governance.schema.json` stays once
`celine.governance.validation` is available — it probably should, because it is what lets the
schema conformance test run with no network.

### Settled by the migration, 2026-09-01

Both, and the second differently than expected. Recorded here because this section asked the
questions, not because an ADR is a progress log.

**`policy` survives.** `DataspacePolicy` carries `audience`, `obligations` and `consent`,
which celine does not model, so it is not a synonym for `DataspaceConfig`. It is a subclass's
extra field, merged by ds after `merge_rules` has done the rest.

**The schema file stays, and the reason it stays changed.** `celine-utils` ships the schema
inside the wheel, so the conformance test reads it from the installed package — which is not
merely offline but *version-locked to the parser*, which a cache never was. The copy under
`schemas/` remains because ds **publishes** it for producers, and it is now refreshed from
the dependency rather than fetched from celine's docs site. Its staleness was not
hypothetical: when this was settled it was three root properties behind, and nothing had
failed.

The minimum version is `2.5.0`, and that is a consequence worth naming here rather than only
at the pin. This ADR argued from `extra="ignore"` making subclassing safe; in 2.4 that same
setting made every shared merge lossy for a subclass, because each one validated its result
into the base class by name. 2.5 takes the class from its operands. **Installing 2.4 under
this code would not fail to import — it would silently drop the fields the subclass exists to
carry**, which is the defect this decision was taken to end.
