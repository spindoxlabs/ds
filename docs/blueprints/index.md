# Blueprints

This section renders two public data-space blueprints into a single, citable reference.
It exists to serve two purposes at once:

1. **A requirements source** — what a data space of this kind is expected to implement.
2. **A benchmark baseline** — a stable, addressable set of statements that an
   implementation can later be measured against, item by item.

Both purposes fail on imprecision, so these pages favour fidelity to the source over
readability wherever the two conflict. Upstream terminology, capitalisation, ampersands,
protocol names, specification versions, IRIs and legal citations are reproduced exactly
as published. Where a source is ambiguous, incomplete or self-contradictory, that is
recorded as a finding rather than resolved by inference.

## The sources

| | DSSC Blueprint | Blueprint of the Common European Energy Data Space |
|---|---|---|
| **Publisher** | Data Spaces Support Centre | Interoperability Network for the Energy Transition (int:net), c/o Fraunhofer-Gesellschaft zur Förderung der angewandten Forschung e. V., Hansastrasse 27c, 80686 Munich, Germany |
| **Version** | 3.0 | 3.0 |
| **Date** | not stated in the source (see below) | September 2025 |
| **Canonical reference** | <https://blueprint.dssc.eu/> | DOI [`10.5281/zenodo.17116750`](https://doi.org/10.5281/zenodo.17116750) |
| **Licence** | not stated in the source | CC BY 4.0 |
| **Copyright** | © Data Spaces Support Centre | © 2024 by int:net |
| **Funding** | EU Digital Europe Programme, grant agreement nº 101083412 | Horizon Europe Research and Innovation Programme, grant agreements nº 101070086, 101069831, 101069694, 101069839, 101069287, 101069510 |
| **Retrieved** | 2026-07-31 | 2026-07-31 |

Three notes on the table above, each of which is a property of the sources rather than
of this rendering:

- **The DSSC Blueprint states no licence.** No licence statement appears anywhere in the
  v3.0 material. The only licensing language in the blueprint concerns *data* licensing
  as a subject matter, not the document's own terms.
- **The DSSC Blueprint v3.0 carries no publication date.** It describes itself as "the
  concluding version of the DSSC project". Its own timeline records v0.5 in September
  2023, v1.0 in March 2024, v1.5 in September 2024 and v2.0 in March 2025, and stops
  there. No month is given for v3.0.
- **The CEEDS copyright year (2024) precedes its version date (September 2025).** Both
  are printed in the document's own front matter.

## How the two relate

CEEDS is an energy-domain **specialisation** of the DSSC Blueprint, not an alternative to
it: it adopts the DSSC's data-space concept and building-block structure and adds the
energy sector's standards, roles, market models and use cases.

That relationship carries an important qualification. **CEEDS v3.0 never cites DSSC
v3.0.** It attributes its data-space definition to DSSC Blueprint v1.0, its
building-block grid to v1.0, and its governance baseline to v2.0. It also frames the
specialisation as an intention rather than an accomplished fact — "the objective in the
future is that the CEEDS architecture is a specialization of the mandatory part" of the
DSSC. [`comparison.md`](comparison.md) compares the two and states this caveat wherever
it bears on a claim.

## Contents

- **[DSSC Blueprint](dssc/index.md)** — nine building blocks in three categories, two
  framing sections, the eleven service definitions, cross-cutting concerns, the business,
  governance and legal building blocks, the co-creation method, and a consolidated
  glossary.
- **[CEEDS Blueprint](ceeds/index.md)** — the data-space concept, five energy business
  use cases, the proposed architecture, implementation details from the Energy Data Space
  Cluster Projects, governance, interoperability, and a consolidated energy-standards
  reference.
- **[Comparison](comparison.md)** — how the two relate, structurally and requirement by
  requirement.

## How to cite a requirement

Every requirement on these pages carries a stable identifier:

```
DSSC-<BB>-<NN>          CEEDS-<AREA>-<NN>
```

**These identifiers are ours, not the sources'.** Neither blueprint numbers its
requirements, and neither numbers its building blocks — DSSC's are named, never
`BB01`-style. The index exists so that code can be benchmarked against a fixed target;
it is a local convention and carries no upstream authority. IDs are permanent: they are
never renumbered, only appended.

`<BB>` and `<AREA>` codes, and the page each belongs to, are listed in
[`dssc/index.md`](dssc/index.md) and [`ceeds/index.md`](ceeds/index.md).

Each requirement row records:

| Column | Meaning |
|---|---|
| **ID** | our identifier, stable and permanent |
| **Requirement** | one testable statement, in the source's own terms |
| **Force** | the source's normative force, never ours: `must`, `should`, `may`, `recommended` or `informative` |
| **Source** | where it comes from — upstream filename and section for DSSC, chapter and line range for CEEDS |

**Read `Force` before treating a row as a target.** It is the source's, not a judgement
of importance. `informative` means the source states something descriptively, without
obligation, and a large share of rows are `informative` — particularly across the CEEDS
chapters, which survey what projects built rather than specifying what implementations
must do.

### Two things a benchmark author needs to know before starting

**DSSC mandates capabilities while declining to mandate specifications.** Several building
blocks say in one section that certain capabilities are *required*, and in another that
"there are no mandatory specifications a dataspace shall follow" for that capability. This
is a coherent editorial stance, but it means a substantial number of DSSC requirement rows
are not testable as written: they oblige an outcome without fixing a way to verify it.

**Specification versions are largely unpinned.** Across both blueprints, most named
standards carry no version, edition or profile — and where a version exists it is often
only inside a hyperlink rather than in the prose. Any conformance claim resting on these
pages has to supply its own version anchors and say so. The affected standards are
identified per page in each "Standards and protocols" table, which records "not stated"
rather than inferring a version.

## What is not here

These pages describe the blueprints and nothing else. **No claim about this codebase —
what it implements, supports or lacks — appears anywhere in this section.** Assessing an
implementation against these requirements is separate work; mixing it in would turn a
requirements source into a self-assessment.
