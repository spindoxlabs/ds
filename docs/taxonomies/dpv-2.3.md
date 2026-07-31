# DPV 2.3 — the external vocabulary the purpose taxonomy aligns to

ds carries its own purpose taxonomy in the ODRL profile
(`libs/governance/src/ds/governance/profiles/energy.yaml`). Each local concept
declares a `dpv_mapping` to a term in the **W3C Data Privacy Vocabulary**, so a
reader outside this dataspace can tell what a purpose means without reading our
YAML.

This page records **which DPV version we align to, which terms we cite, and why
each alignment is the one it is** — so the claim can be re-checked rather than
trusted, and so an upstream change is visible as a diff instead of as silent rot.

!!! warning "The alignment is documentation, never enforcement"
    `odrl:isA` matching follows **only** the local `broader` chain in
    `energy.yaml`. `dpv_mapping` is never consulted when deciding whether a
    consent covers a request — see `OdrlProfile.is_a`
    (`libs/governance/src/ds/governance/models.py`). A `broadMatch` to a generic
    DPV term would otherwise let an unrelated use satisfy a specific consent.
    Getting a mapping wrong here publishes a false interop claim; it does not
    widen access.

---

## 1. The version we pin

| | |
|---|---|
| Specification | Data Privacy Vocabulary (DPV) **v2.3** |
| Published | **25 February 2026** (`dcterms:modified "2026-02-25"@en`) |
| Publisher | W3C Data Privacy Vocabularies and Controls Community Group (DPVCG) |
| Canonical namespace | `https://w3id.org/dpv#` |
| Prefix used here | `dpv:` |
| Specification URL | <https://w3id.org/dpv> → <https://w3c-cg.github.io/dpv/2.3/dpv/> |
| Purposes module (source of every quote below) | <https://w3c-cg.github.io/dpv/2.3/dpv/modules/purposes.ttl> |

`https://w3id.org/dpv#` stays the **IRI we write into the profile** even though
the documentation is served from `w3c-cg.github.io` — w3id is the permanent
identifier and the GitHub host is where the current draft is rendered.

DPV is a Community Group report, **not a W3C Standard**. That is the normal
status for DPV and does not weaken the alignment; it is noted because §6 depends
on the distinction.

---

## 2. Purpose hierarchy — the branches we use

Verbatim `skos:definition` strings from the purposes module. Indentation is the
declared parent (`skos:broader` / `rdfs:subClassOf`).

```
dpv:Purpose
├─ dpv:ServiceManagement
│    "Purposes associated with the management of services or products"
│  ├─ dpv:ServiceProvision
│  │    "Purposes associated with providing service or product or activities"
│  ├─ dpv:ServiceMonitoring
│  │    "Purposes associated with the monitoring of services or products to
│  │     understand their performance and utilisation with a view to inform
│  │     their management"
│  │  └─ dpv:ServiceUsageAnalytics
│  │       "Purposes associated with conducting analysis and reporting related
│  │        to usage of services or products"
│  └─ dpv:ServiceOptimisation
│       "Purposes associated with optimisation of services or activities"
│     ├─ dpv:OptimisationForConsumer
│     │    "Purposes associated with optimisation of activities and services
│     │     for consumer or user"
│     └─ dpv:OptimisationForController
│          "Purposes associated with optimisation of activities and services
│           for provider or controller"
│        ├─ dpv:IncreaseServiceRobustness
│        │    "Purposes associated with improving robustness and resilience of
│        │     services"
│        └─ dpv:InternalResourceOptimisation
│             "Purposes associated with optimisation of internal resource
│              availability and usage for organisation"
├─ dpv:ResearchAndDevelopment
│    "Purposes associated with conducting research and development for new
│     methods, products, or services"
├─ dpv:FulfilmentOfObligation
│  │  "Purposes associated with carrying out data processing to fulfill an
│  │   obligation"
│  └─ dpv:FulfilmentOfContractualObligation
│       "Purposes associated with carrying out data processing to fulfill a
│        contractual obligation"
├─ dpv:PublicBenefit
│  │  "Purposes undertaken and intended to provide benefit to public or society"
│  ├─ dpv:ImprovePublicServices
│  │    "Purposes associated with improving the provision of public services,
│  │     such as public safety, education or law enforcement"
│  ├─ dpv:CombatClimateChange
│  │    "Purposes associated with combating the causes and consequences of
│  │     climate change, including reducing gas emissions and fighting
│  │     emergencies such as floods or wildfires"
│  ├─ dpv:ImproveTransportMobility
│  │    "Purposes associated with improving traffic, public transport systems
│  │     or costs for drivers"
│  ├─ dpv:ProvideOfficialStatistics
│  └─ dpv:DataAltruism
└─ dpv:OrganisationGovernance
   │  "Purposes associated with conducting activities and functions for
   │   governance of an organisation"
   └─ dpv:OrganisationRiskManagement
        "Purposes associated with managing risk for organisation's activities"
```

For reference, the purposes module declares **17 direct children of
`dpv:Purpose`**: `AccountManagement`, `CommercialPurpose`,
`CommunicationManagement`, `CustomerManagement`, `EnforceSecurity`,
`EstablishContractualAgreement`, `FulfilmentOfObligation`,
`HumanResourceManagement`, `Marketing`, `NonCommercialPurpose`,
`OrganisationGovernance`, `Personalisation`, `PublicBenefit`, `RecordManagement`,
`ResearchAndDevelopment`, `ServiceManagement`, `VendorManagement`.

---

## 3. DPV has no energy vocabulary — this is why a local taxonomy exists

Checked directly against the 2.3 purposes module: **no term whose name contains
*Energy*, *Grid*, *Electricity*, *Forecast*, *Planning* or *Predict* exists in
core DPV.** The only `Monitor`/`Predict` hits are personnel-related
(`dpv:PersonnelMonitoring`, `dpv:PersonnelPerformancePrediction`,
`dpv:CustomerSolvencyMonitoring`) and unrelated to this domain.

DPV is deliberately domain-neutral. So the local taxonomy is not a workaround
for a gap we should be closing upstream — it is the intended extension point,
and every local concept is expected to sit **narrower than** some DPV term. That
is why every relation below is `broadMatch` and none is `exactMatch`.

---

## 4. The alignment

`skos:broadMatch` on a local concept means: *the DPV term is broader than ours.*
An `exactMatch` would be a claim that the two are interchangeable, which is never
true here — every local concept is an energy-domain specialisation.

| ds concept | `broader` (local) | DPV 2.3 term | Why this term |
|---|---|---|---|
| `EnergyCommunityOperation` | — (root) | `dpv:ServiceProvision` | Operating a REC on behalf of its members is the provision of a service to those members. |
| `IncentiveCalculation` | `EnergyCommunityOperation` | `dpv:FulfilmentOfContractualObligation` | The community has a **contractual** duty to compute and distribute incentives — `sharing-offers.yaml` declares this offer under `dpv:Contract`, not consent. The contractual child is more truthful than the generic `FulfilmentOfObligation`. |
| `CostOptimization` | `EnergyCommunityOperation` | `dpv:OptimisationForConsumer` | Reducing energy cost *for the member* is optimisation for the consumer, not the controller. |
| `FlexibilityResearch` | `EnergyCommunityOperation` | `dpv:ResearchAndDevelopment` | Studying shiftable consumption to plan community flexibility. |
| `GridMonitoring` | — (root) | `dpv:ServiceMonitoring` | "monitoring … to understand their performance and utilisation with a view to inform their management" is close to a definition of grid monitoring. Electricity distribution is the service. |
| `GridResilience` | — (root) | `dpv:IncreaseServiceRobustness` | Verbatim: "improving robustness and **resilience** of services". The nearest thing to an exact match in DPV for this concept. |
| `EnergyForecasting` | — (root) | `dpv:ServiceOptimisation` | Forecasts of generation, consumption and grid state exist to operate the system better. Sits under `OptimisationFor*` rather than beside it, because the beneficiary varies by dataset. |
| `EnergyPlanning` | — (root) | `dpv:ServiceManagement` | Planning infrastructure, capacity and investment is management of the service rather than its delivery, optimisation or monitoring. Deliberately the generic parent — see the caveat below. |
| `PVPotentialAssessment` | `EnergyPlanning` | `dpv:ServiceProvision` | Assessing rooftop potential and ROI is delivered *as* an assessment service to a building owner or installer. |

### Two alignments that are weaker than the rest

- **`EnergyPlanning` → `dpv:ServiceManagement`** is a top-level term, so the
  claim is thin: it says little more than "this is about managing a service".
  Nothing narrower in core DPV fits — `PublicBenefit` would assert a societal
  purpose that a commercial PV ROI product does not have. See §6 for the
  sector-extension term that fits properly but is not usable yet.
- **`EnergyForecasting` → `dpv:ServiceOptimisation`** reads the *reason* for
  forecasting rather than the act. A weather observation dataset aligned this way
  inherits an energy framing it does not have on its own. This is a known
  imprecision, accepted because the datasets under this purpose in this dataspace
  are consumed for energy operation.

Both are recorded here rather than smoothed over, because a `dpv_mapping` that
looks confident and is merely adequate is worse than one annotated as adequate.

---

## 5. What changed between 2.2 and 2.3

The profile previously cited **v2.2** (31 October 2025). The `ServiceProvision`
branch was **re-parented** in 2.3, which is exactly the kind of drift this page
exists to catch:

| Term | Parent in 2.2 | Parent in 2.3 |
|---|---|---|
| `dpv:ServiceProvision` | `dpv:Purpose` | `dpv:ServiceManagement` *(new)* |
| `dpv:ServiceOptimisation` | `dpv:ServiceProvision` | `dpv:ServiceManagement` *(new)* |
| `dpv:ServiceUsageAnalytics` | `dpv:ServiceProvision` | `dpv:ServiceMonitoring` *(new)* |

`dpv:ServiceManagement` and `dpv:ServiceMonitoring` do not exist in 2.2. No term
ds cites was **removed** or renamed, so the upgrade does not invalidate any
existing mapping — it adds two intermediate concepts, one of which
(`ServiceMonitoring`) turned out to be a better parent for `GridMonitoring` than
the `dpv:PublicBenefit` the profile used to claim.

The following mappings were **corrected** while adopting 2.3:

| ds concept | Was | Now | Reason |
|---|---|---|---|
| `GridMonitoring` | `dpv:PublicBenefit` | `dpv:ServiceMonitoring` | `PublicBenefit` is a top-level societal-good term; grid monitoring by a DSO is service monitoring, and asserting public benefit overstated it. |
| `IncentiveCalculation` | `dpv:FulfilmentOfObligation` | `dpv:FulfilmentOfContractualObligation` | The obligation is contractual and the offer already says so. |

---

## 6. Sector extension — precise, but not usable yet

DPV publishes an **Infrastructure sector extension** which contains the terms
this domain actually wants:

| Term | Definition | Parent |
|---|---|---|
| `sector-infra:InfrastructureManagement` | "Purposes associated with management of infrastructure" | `dpv:Purpose` |
| `sector-infra:CriticalInfrastructureManagement` | "Purposes associated with management of infrastructure considered essential or critical for functioning of society and economy as defined by a government or a legislation" | `InfrastructureManagement` |
| `sector-infra:CriticalEnergyManagement` | "Purposes associated with management of critical energy infrastructure and services" | `CriticalInfrastructureManagement` |
| `sector-infra:CriticalElectricityManagement` | "Purposes associated with management of critical electric energy infrastructure and services" | `CriticalEnergyManagement` |

- Namespace: `https://w3id.org/dpv/sector/infra#`, prefix `sector-infra`
- Its purposes **are** declared as `dpv:Purpose` subclasses, so they are usable
  with `dpv:hasPurpose`
- Published 25 February 2026 alongside 2.3, but as a **separate Draft Community
  Group Report — explicitly not a normative part of DPV 2.3**

`CriticalElectricityManagement` would be a materially better parent for
`GridMonitoring`, `GridResilience` and `EnergyPlanning` than any core term. It is
**not** in the profile today for two reasons:

1. `PurposeConcept.dpv_mapping` holds **one** mapping, so citing the sector term
   would mean dropping the core-DPV one. A reader who resolves only core DPV
   would then see no alignment at all.
2. Citing a separate draft extension is a stronger interop commitment than citing
   core DPV, and should be a deliberate decision rather than a side effect.

**Decision: stay on core DPV only, for now.** A single normative, stable IRI per
concept is worth more than a more precise one from a draft that can be renamed
under us — and the alignment is documentation, so precision here buys less than
it would if enforcement followed it. The sector terms are recorded above so the
option stays open rather than being rediscovered.

**If we later want both**, `dpv_mapping` becomes a list and `/ns/policy` emits
one `skos:*Match` triple per entry — SKOS already allows multiple match
predicates on a concept. A contained change to `models.py`, the namespace
endpoint, `check_purpose_taxonomy`, and `schema_export.purpose_vocabulary`.

---

## 7. Re-checking this page

The alignments were verified by fetching the module Turtle and extracting each
cited term's literal `skos:definition` and parents — twice, with independently
worded extractions, to catch a bad read. Two claims were checked negatively as
well (no energy/grid/forecast term in core DPV; no Energy sector extension),
because an absent term is what makes the local taxonomy necessary and an
unverified absence would be the easiest thing to get wrong.

To re-check after a DPV release:

```bash
curl -fsSL https://w3c-cg.github.io/dpv/<version>/dpv/modules/purposes.ttl \
  | grep -A6 -E '^dpv:(ServiceManagement|ServiceProvision|ServiceMonitoring|ServiceOptimisation|OptimisationForConsumer|IncreaseServiceRobustness|ResearchAndDevelopment|FulfilmentOfContractualObligation) '
```

Confirm every IRI in `energy.yaml`'s `dpv_mapping` still resolves and that no
cited term was re-parented in a way that changes what the `broadMatch` claims.
`check_purpose_taxonomy` only asserts that the IRI is absolute and that the
relation is one of the five SKOS match properties — **a wrong-but-well-formed
IRI passes every test in this repo**, so this page and a human reading it are the
only real gate.

---

## 8. References

- DPV 2.3 specification — <https://w3c-cg.github.io/dpv/2.3/dpv/>
- DPV 2.3 purposes module (Turtle) — <https://w3c-cg.github.io/dpv/2.3/dpv/modules/purposes.ttl>
- DPV 2.2 specification (superseded, 31 October 2025) — <https://w3c-cg.github.io/dpv/2.2/dpv/>
- Infrastructure sector extension — <https://w3c-cg.github.io/dpv/2.3/sector/infra/>
- Permanent identifier / namespace — <https://w3id.org/dpv>
- DPVCG home — <https://w3c-cg.github.io/dpv/>
- The profile itself — `libs/governance/src/ds/governance/profiles/energy.yaml`
- How purposes are enforced — [ds-governance](../services/libs/governance.md) (the taxonomy,
  and the ODRL a rule becomes), [ds-connector](../services/connector.md) (the purpose check on
  every data-plane decision), [Rulebook · Policies](../rulebook/policies.md),
  [Rulebook · Personal data](../rulebook/personal-data.md)
