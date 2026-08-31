# The characterisation corpus

**This directory is input to a test, not configuration.** Nothing loads it at runtime.

It exists for
[`the-governance-parser-belongs-upstream`](https://github.com/spindoxlabs/ds/blob/main/docs/decisions/ADR-0013-governance-shape-comes-from-celine-utils.md):
ds is replacing its own governance parser with `celine.governance`, and the whole claim of
that migration is that **behaviour does not change**. Nothing said what the behaviour was.
`tests/tests/test_characterisation.py` pins it — every dataset key in this corpus, resolved,
field by field — and runs `celine.governance` over the same corpus as a second implementation.

## What is here, and why each file earns its place

| Path | Provenance | What it exercises |
|---|---|---|
| `demo3/*.governance.yaml` | **Vendored copies** of `celine-eu/demo3` `pipelines/apps.legacy/{grid,rec_flexibility,rec_it,rec_metering}/governance.yaml` | Producer-authored files, in the canonical grammar, written by nobody in this repository: `defaults` carrying a whole `dcat` block and `dataspace.purpose`, per-dataset overlay of `tags` / `expose` / `row_filters` / `ownership` / `access_level`, `license: null` and `documentation_url: null` stated explicitly, and `dataspace.odrl_action` — a field ds models nowhere. 29 dataset keys. |
| `overlay/governance.yaml` | Copy of `services/connector/governance-rec/governance.yaml` | The base half of an overlay pair. |
| `overlay/governance.deployment.yaml` | Written for this corpus | The deployer overlay. Every merge rule that is *not* "override wins" — `ownership` replacement, `tags` union, `purpose` union, `consent_required` OR, `expose` withdrawal, nested `data_address.base_url` rebinding with the siblings surviving — plus a source only the overlay declares. |

The corpus **also** covers three files in their own place in the tree, read where they live
rather than copied: `services/connector/governance-{rec,grid-operator}/governance.yaml` and
`services/connector/tests/fixtures/governance.yaml`. Copying those would let the copy drift
from the file the stack actually syncs, which is the one thing this corpus must not do.

## Why the demo3 files are copies

They are the opposite case: they live in another repository, on another release cycle, and
this repository has no checkout of it in CI. A copy is the only way a producer-authored file
can be in the corpus at all. **The copy is a snapshot and is allowed to go stale** — its job
is to be a realistic file, not the current one. Refresh it deliberately if the grammar moves;
do not wire it to a path outside this repository.
