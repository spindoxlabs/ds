# ds-governance

`import ds.governance`. Owns the governance vocabulary: parses `governance.yaml` and
`sharing-offers.yaml`, resolves a rule for a dataset key, converts it into an ODRL Offer and
the three EDC payloads, validates a file before import, emits audit evidence, and generates
the JSON Schemas this repository publishes.

**The single place a governance declaration becomes an enforceable policy constraint.**
`services/connector` is its only in-repo importer.

## References

| | |
|---|---|
| Requirements | [DSSC · Access & Usage Policies Enforcement](../../docs/blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) · [DSSC · Data, Services & Offerings Descriptions](../../docs/blueprints/dssc/data-value-creation-enablers/data-services-and-offerings-descriptions.md) · [DSSC · Data Models](../../docs/blueprints/dssc/data-interoperability/data-models.md) |
| Rules | [Rulebook · Policies](../../docs/rulebook/policies.md) — the profile's required elements and the five conflict-resolution rules · [Rulebook · Catalogue and metadata](../../docs/rulebook/catalogue-and-metadata.md) · [Rulebook · Data models](../../docs/rulebook/data-models.md) |
| Code as committed | [docs/services/libs/governance.md](../../docs/services/libs/governance.md) |

## Where to work

| Task | File |
|---|---|
| Governance file shape | `models.py` |
| Sharing offer shape, `user_visible_hash` | `sharing.py` |
| ODRL / EDC payload emission | `mapper.py` |
| Rule resolution and overlays | `resolver.py` |
| The validation gate | `compliance/{checks,consent_checks,validator}.py`, `cli.py` |
| The shipped ODRL profile | `profiles/energy.yaml` |

## Rules that are not visible from the code

- **Keep the schema domain-neutral.** The energy profile is one shipped, overridable
  instance; nothing in `models.py` or `sharing.py` may assume energy concepts.
- **Purposes are declared, never derived from tags.** `policy.purpose[]` is the only runtime
  source. A tag is a *topic*; a purpose is a *reason for processing*, and `tags` is overloaded
  anyway. `tag_to_purpose` survives only as a scaffolding default.
- **`is_a()` walks `broader` and nothing else.** Following a `dpv_mapping` `broadMatch`
  during enforcement would let a consumer naming a generic DPV term satisfy a member's
  specific consent. `test_is_a_never_follows_dpv_mapping` pins it. `purpose_slug()` returns
  `None` for anything unknown — never a wildcard.
- **One `odrl:purpose` constraint per permission** — `isA` for one purpose, `isAnyOf` for
  several. Constraints inside a permission are ANDed, so one per purpose would demand a
  consumer's use serve all of them at once.
- **The multi-valued `isAnyOf` operand survives only because of a patched EDC class** in
  `services/edc-extensions`. Do not replace it with `odrl:or` of scalar `isA`: tested against
  a running EDC, that fails JSON-LD compaction and 500s the whole Management API list
  response, emptying the DSP catalogue. `test_several_purposes_stay_one_multi_valued_isanyof`
  pins the shape.
- **`resolve()` falls back to `defaults` for an unknown key.** Right for catalogue rendering,
  wrong for a consent write. Callers needing strictness test membership in `config.sources`
  first — the connector does this in `services/consent_vocabulary.py::resolve_dataset`.
- **`user_visible_hash()` excludes `datasets[]` by design.** Which datasets back an offer is
  a schema-migration concern nobody was shown, so changing them must not invalidate consent.
- **`schemas/` is generated from the models, never hand-edited** (`task -d libs/governance
  schema:generate`, no-diff tested). `purpose-vocabulary.json` carries the *active profile's*
  slug enum, which no static schema can — regenerate it whenever the profile changes.

## The validation gate

```bash
task compliance:validate           # offline, against the YAML seeds
task compliance:validate:runtime   # against a running identity-registry
task compliance:evidence           # DCAT-AP catalog + ODRL offers → reports/compliance
```

It validates **input**. It deliberately does not re-assert the mapper's output, which
`tests/test_mapper.py` covers.

`compliance:validate:runtime` needs a **token** — `/admin/participants` and `/owners/resolve`
are both scoped — and it refuses rather than skipping when it cannot read them: a caller naming
a registry asked for `owner-participant`, so a quieter pass would hide the check not running.
That is not hypothetical; it is how `GOV-19` survived. `ControllerLookup.available`
distinguishes "no registry to check against" (warning) from "the registry has no such
controller" (error).

**`controller_role` is *not* checked against participant roles.** Participant roles are DSP
capacities the registry pins to `{provider, consumer}`; a `controller_role` is an unbundled
controller function. The vocabulary is declared by the producer in `controller_roles` beside the
offers, so the check is offline — see
[docs](../../docs/services/libs/governance.md#controller_roles-the-unbundling-vocabulary) and
rulebook `D-11a`. Reintroducing the registry join re-creates `GOV-20`: an unsatisfiable check
that passes by comparing against an empty set.

**Pass `--participant-did` outside dev**, or the ODRL assigner falls back to a dev hostname.

`cd libs/governance && uv sync --extra dev && pytest`.
