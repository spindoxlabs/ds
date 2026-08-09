# Catalogue and metadata

How offerings are published, described and found.

Covers `DSSC-PUB-01`–`45` and `DSSC-DSO-01`–`41`.

## 1. Catalogue architecture

`DSSC-PUB-06` requires the governance authority to decide the architectural option for
catalogue services. There are three common options: purely distributed (each participant
serves its own, consumers query each), a central catalogue, or a federated index over
distributed catalogues.

**Decision: distributed catalogues with an optional federated index.**

- Every participant serves its own catalogue from its own control plane over DSP. This is
  the authoritative surface: an offering exists because its provider serves it.
- `ds-federated-catalog` crawls registered participants and republishes the union as a
  single read-only `dcat:Catalog`. It is a **convenience index, never an authority**. A
  consumer that negotiates does so against the provider, not the index.
- The index holds no database. Nothing survives a restart, by design — a stale index is a
  worse failure than an empty one.

| # | Rule | Status |
|---|---|---|
| C-1 | Every participant implements or uses a catalogue service as part of its control plane (`DSSC-PUB-05`) | **Enforced** — the EDC serves it; a participant without one is not reachable over DSP |
| C-2 | The federated index is advisory. A discrepancy between index and provider is resolved in favour of the provider | **Declared** |
| C-3 | The index crawls only active participants | **Enforced** — `load_providers_from_registry` passes `active_only=true` *and* filters the returned `active` field; a payload that omits it is read as not active. Belt and braces on purpose: the identity-registry route already narrows for any caller without `identity-registry.admin`, which is someone else's guard |
| C-4 | The index authenticates to the connector it crawls through | **Enforced** — the crawl mints a `svc-ds-federated-catalog` client-credentials token per cycle and `POST /consumer/catalog` requires `connector.consumer.read`. Landed together, as it had to be |

## 2. Syntax

**Decision: DCAT-AP within DSP, ODRL for policy, JSON-LD serialisation.**

`DSSC-PUB-08` and `DSSC-SVD-35` require DCAT-AP as the syntax for exchanging data-product
metadata within DSP; `DSSC-PUB-37` requires DCAT to be extended by an application profile
for the specific data space. `CEEDS-STD-10` recommends DCAT, which is weaker — this data
space follows the stricter statement.

| Element | Class / property |
|---|---|
| Catalogue | `dcat:Catalog` |
| Offering | `dcat:Dataset` with an attached `odrl:hasPolicy` |
| Distribution | `dcat:Distribution`, `dcat:accessURL`, `dcat:mediaType` |
| Descriptive metadata | `dct:title`, `dct:description`, `dct:identifier`, `dct:publisher`, `dct:license`, `dct:issued`, `dct:source`, `dct:conformsTo` |
| Keywords | `dcat:keyword` — a topic, never a policy statement |
| Policy | `odrl:Offer` with permissions, prohibitions, obligations |

| # | Rule | Status |
|---|---|---|
| C-5 | Access and usage control of offerings are expressed as ODRL policies (`DSSC-PUB-38`) | **Enforced** |
| C-6 | `dcat:keyword` carries no policy meaning. A dataset's permitted purposes come from `policy.purpose[]` and nowhere else | **Enforced** — `tag_to_purpose` is an authoring default used by scaffolding only |
| C-7 | A catalogue includes at least one `dcat:DataService` referencing the service that provides its datasets (`DSSC-PUB-41`) | **Enforced** — shape in `ds.governance.dcat`, emitted by both catalogues this platform publishes. The federated index names **each crawled source's** endpoint, not its own: it provides nothing and is advisory (`C-2`), so the service a consumer needs is the provider's |
| C-8 | A catalogue response references its entries via `dcat:record` rather than inlining them (`DSSC-PUB-45`) | **Enforced, with a declared deviation** — every entry now carries a `dcat:CatalogRecord` (`foaf:primaryTopic`, `dct:modified` = crawl time, `dct:source` = originating catalogue). `dcat:dataset` stays inlined alongside; `PUB-45` says *rather than*. **The deviation is now a decision, not a gap** (2026-08-09): DSP's catalogue spec says a Catalog **MUST** have zero to many Datasets, so `PUB-45`'s form would break a protocol MUST on the surface a counterparty actually reads. See [scope-and-deviations](scope-and-deviations.md) §3.6 |

## 3. The minimum metadata set

`DSSC-DSO-19` and `-21` require the data space to decide what the minimum metadata set is
per type of data product, and to record it here. `DSSC-DSO-16`, `-17`, `-18` and
`DSSC-DEX-02` state the three categories it must cover.

**Decision.** Every offering, of every type, carries the following. The authoring surface is
`services/connector/governance-rec/governance.yaml`; the field names below are that file's.

### Mandatory for every data product

| Category | Field | Blueprint row |
|---|---|---|
| Identity | dataset key (the map key), `dataspace.asset.id` | — |
| Content | `title`, `description`, `source_system` | `DSO-16` |
| Content | `license` | `DSO-16` |
| Content | `classification` — one of `green`, `yellow`, `red`, `pii` | `DSO-16` (use restrictions) |
| Content | `retention_days` | `DSO-16` |
| Representation | `dataspace.asset.content_type` | `DSO-17` |
| Representation | `dataspace.medallion` — the refinement stage (`bronze` / `silver` / `gold`) | `DSO-17` |
| Accessibility | `dataspace.data_address` — type, base URL, proxy behaviour | `DSO-18`, `DEX-02` |
| Accessibility | `access_level` — one of `open`, `internal`, `restricted`, `secret` | `DSO-18` |
| Policy | `dataspace.purpose[]` — the permitted reasons for processing | `AUP-01` |
| Attribution | `ownership[]` — at least one owner with a type | — |

### Additionally mandatory where the product contains personal data

| Field | Meaning |
|---|---|
| `classification: pii` | Declares it. Drives the automatic prohibitions in [Policies](policies.md) §3 |
| `dataspace.consent_required: true` | The consent gate |
| `dataspace.sharing_offers[]` | The offers a subject is actually asked about. Each must resolve |
| `row_filters[]` | How rows are narrowed to the subjects who consented |

**A dataset names its offers; an offer never names datasets.** Offers are declared by
whoever declares the dataset, so an offer listing arbitrary dataset keys would let one
producer write the consent text for another's data.

| # | Rule | Status |
|---|---|---|
| C-9 | An offering missing any mandatory field is not published | **Enforced** — Pydantic models plus `task compliance:validate` |
| C-10 | A `pii` dataset with an unresolvable sharing offer is not published — advertising a consent gate that can never open is worse than not publishing | **Enforced** |
| C-11 | An empty `purpose[]` is never a wildcard for personal data | **Enforced** — fails closed |
| C-12 | Metadata is checked for compliance with the standards it claims (`DSO-11`) | **Enforced.** The `dcat-ap` check in `ds-governance validate` splits DCAT-AP's own obligation levels: **mandatory** properties (`dct:title`, `dct:description`) are errors, **recommended** ones (`dcat:theme`, `dct:license`, `dct:accrualPeriodicity`, `dct:spatial`, `dct:temporal`) are warnings. It checks the *governance input*, not the emitted record — both mandatory properties have a fallback in the emitter, so a file declaring neither publishes a structurally valid document that says nothing, and a validator reading the output would pass it. `libs/governance/tests/tests/test_declared_not_enforced.py`, including one case asserting this repository's own governance files conform |
| C-13 | Metadata is checked for compliance with this rulebook (`DSO-12`) | **Enforced** 2026-08-09. Two halves: the rulebook is projected to `rules.json` and CI checks the record against itself (`GOV-18`); and every finding `ds-governance validate` emits now **cites the rule ids it enforces** — `compliance/rulebook.py`, one map, with `test_rulebook_citations.py` asserting every id resolves in the projection. **The gap was attribution, not coverage:** of the 35 rules on this page and [Data models](data-models.md), most already had a named check (`C-9`–`C-12`, `C-14`, `M-1`–`M-4`, `M-7`, `M-9`, `M-10`) and the rest are runtime properties (`C-15`–`C-20`) or process declarations (`C-2`, `M-5`, `M-6`, `M-12`–`M-14`) no validator can test — so the plan's framing, *decide which rules are checkable*, was the wrong question. A check that enforces a model invariant rather than a rulebook decision cites nothing, deliberately: inventing a citation for symmetry is the failure this removes |
| C-14 | Metadata is checked for completeness (`DSO-13`) | **Enforced** for the mandatory set above |

## 4. The offering lifecycle

`DSSC-PUB-02` requires publish / update / remove, and `DSSC-PUB-12`–`32` specify the
pre-conditions, success paths and denial paths for each.

| Operation | How | Denial path |
|---|---|---|
| Publish | `POST /provider/sync` pushes `governance.yaml` into EDC as assets, policy definitions and contract definitions | Caller must hold `connector.provider.write`; a dataset failing validation is not published |
| Update | The same call. The sync recomputes from the file — it is declarative, not incremental | Same |
| Remove | `dataspace.expose: false`, then sync | Same |
| Discover | DSP catalogue request against the provider, or `GET /catalog` against the index | Provider-side: DSP requires a DCP-verified counterparty |

| # | Rule | Status |
|---|---|---|
| C-15 | A publisher must be a registered participant, authenticated as such (`PUB-13`) | **Enforced** — `connector.provider.write` on a verified token |
| C-16 | A publisher must be authorised for the *owner* whose datasets it publishes (`PUB-14`) | **Enforced** — owner-scoped authority; `ds-e2e --flow user-authority` proves the cross-owner refusal with a real token and a real organisation claim |
| C-17 | An unauthenticated or unauthorised publish, update or remove is **denied** (`PUB-19`, `-23`, `-26`) | **Enforced** |
| C-18 | A removed offering is no longer discoverable (`PUB-25`) | **Enforced** at the provider; the index reflects it only after the next crawl cycle |
| C-19 | A discovering consumer must be a registered participant (`PUB-27`) | **Enforced** over DSP, and on `POST /consumer/catalog` since defect **P0-1** closed. `require_consumer_catalog_caller` authenticates by **either** mechanism and never neither — a service on `connector.consumer.read`, or a natural person presenting a `ConsumerUser` VC-JWT; the `CatalogViewed` event is attributed to whichever proved itself, not to a caller-supplied header. `services/connector/tests/test_consumer_catalog_auth.py` |
| C-20 | An unauthorised consumer's request must not even collect matching offerings (`PUB-32`) | **Enforced** over DSP |
| C-21 | Offering visibility may be restricted to a subset of participants (`PUB-03`) | **Partly enforced**, and **accepted as such 2026-08-09.** Visibility is enforced at negotiation, not at discovery: a participant can see that a dataset exists and be refused a contract for it. A deployment may well hold sensitive datasets, and the containment is `governance.yaml` — `access_level: secret` publishes an offer with zero permissions, and `expose: false` publishes nothing at all — so existence is disclosed only for datasets a producer chose to list. Revisit only for a deployment where the *existence* of a dataset is itself the secret, which is a different requirement from its contents |

**Metadata versioning** (`DSO-14`, `-15`) is **not implemented**. `governance.yaml` is
versioned in git, which is version control of the *file*, not of the metadata across the
data product's lifetime — a consumer cannot ask what an offering's description said when
they negotiated. **Open gap.**

## 5. Open gaps, in priority order

1. ~~**DCAT-AP conformance checking (`DSO-11`)**~~ — **done.** The `dcat-ap` check runs in
   `task compliance:validate`; see `C-12`.
2. **Metadata versioning (`DSO-14`, `-15`)** — needs a design decision first: version the
   offering, or snapshot it into the agreement?
3. **Rulebook conformance (`DSO-12`)** — depends on this section having a machine-readable
   projection, which is the same prerequisite as
   [Participation](participation.md) §5.

## Blueprint rows

**Closed by this page:** `DSSC-PUB-01`, `-02`, `-05`, `-06`, `-08`, `-12`, `-13`, `-14`,
`-15`, `-16`, `-19`–`-32`, `-34`, `-36`, `-37`, `-38`, `-39`, `-42`, `-44`; `DSSC-DSO-01`–
`-06`, `-10`, `-13`, `-16`, `-17`, `-18`, `-19`, `-21`, `-36`; `DSSC-DEX-02`;
`DSSC-SVD-35`; `CEEDS-STD-10`, `-13`, `-14`.

**Open:** `DSSC-PUB-41`, `-45`; `DSSC-DSO-11`, `-12`, `-14`, `-15`. `DSSC-PUB-03` partially
— deviation recorded above. `DSSC-DSO-41` (DCAT-AP-HVD for high-value datasets) — not
applicable until a deployment designates one.
