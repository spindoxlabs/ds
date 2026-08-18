# ds — a data space for energy communities

**Independent organisations publish data to each other under machine-readable contracts,
and the people the data describes decide what may be shared about them.**

`ds` implements both halves. Contract-based exchange between organisations is built on the
[Eclipse Dataspace Components](https://projects.eclipse.org/projects/technology.edc). On top
of that, `ds` addresses the case where the data is *about households* — smart-meter readings,
consumption profiles, flexibility events — and a bilateral contract is not sufficient on its
own, because the person the data describes has rights neither signatory can sign away.

Data-subject consent is therefore a first-class object. It is evaluated at contract
negotiation, while a transfer is running, and on every query, and it filters results **row by
row** before any data leaves the provider. Withdrawal terminates a running transfer.

📖 **[Documentation](https://spindoxlabs.github.io/ds/)** — architecture, the rulebook, the
blueprint requirements, and the deployment reference.

---

## What it runs

One command brings up a three-participant data space — an energy community, a consumer, and
a grid operator — each with its own EDC connector, behind a shared trust anchor, plus a
federated catalogue, provenance and a portal:

```bash
task docker:restart     # 19 containers
task e2e:all            # 18 end-to-end flows against the running stack
```

The exchange it runs end to end is the **consumer-pull** flow:

```
discover in the catalogue → negotiate an ODRL contract → receive an Endpoint Data
Reference → pull the data → every row filtered by the consent of the person it describes
```

with a `did:web` identity for each participant, verifiable credentials presented over the
Dataspace Credential Protocol, and a W3C PROV-O record of what happened.

**Design properties:**

- **The policy decision point fails closed.** With the control plane unavailable,
  negotiation is refused rather than permitted. Asserted against a stopped container on every
  full end-to-end run.
- **Consent withdrawal reaches a running transfer.** The agreement is terminated and
  subsequent queries refused, not only the next negotiation. Recorded as rule `D-17`.
- **The data plane is external.** `ds` addresses it over HTTP and calls it back for a
  per-query authorisation decision; it does not own or copy the data.
- **The catalogue is advisory.** It is a crawler's projection of participant catalogues; the
  provider's connector remains the authority on every decision.

---

## Standards alignment

`ds` is aligned with and inspired by the **[DSSC
Blueprint](https://spindoxlabs.github.io/ds/blueprints/dssc/)** reference architecture, and
specialised for the energy domain through
**[CEEDS](https://spindoxlabs.github.io/ds/blueprints/ceeds/)**, the Common European Energy
Data Space blueprint.

Both are rendered in the documentation as citable requirements — `DSSC-DEX-…`,
`CEEDS-INT-…` — and the [rulebook](https://spindoxlabs.github.io/ds/rulebook/) records this
data space's decision on each one, with an enforcement status and the test that backs it:

| Status | Rules |
|---|--:|
| **Enforced** — implemented, with a test asserting it | 104 |
| **Declared** — a recorded decision rather than a mechanism | 21 |
| **Partly enforced** — implemented, with the remainder stated | 7 |
| **Not enforced** — recorded rather than dropped | 3 |
| | **135** |

The architecture follows the DSSC building blocks throughout: DSP for exchange, DCAT-AP for
catalogue metadata, ODRL 2.2 for policy, the Dataspace Credential Protocol for identity, and
W3C PROV-O for provenance. Where the two blueprints differ — marketplaces are optional in
DSSC and integral in CEEDS — the choice is recorded with its reasoning in
**[the comparison](https://spindoxlabs.github.io/ds/blueprints/comparison/)**.

Deliberate scope boundaries are documented in **[Scope and
deviations](https://spindoxlabs.github.io/ds/rulebook/scope-and-deviations/)**, including
payload semantic models (CIM, SAREF4ENER and their neighbours), which the platform leaves to
the deployment so that it stays domain-agnostic.

---

## Quick start

**Prerequisites** — Docker with Compose v2, [Task](https://taskfile.dev) v3+,
[uv](https://docs.astral.sh/uv/), Node.js, and `tmux` for the hot-reload mode.
Full list: [Prerequisites](https://spindoxlabs.github.io/ds/deployment/prerequisites/).

```bash
task docker:restart     # everything in containers — exercises the images and compose env
task status             # what is running
task e2e:all            # end-to-end verification against the running stack
```

Then open **<http://portal.dataspaces.localhost>** and sign in as
`subject@example.test` (password `subject`) to see the consent plane from a household's
side, or `provider@example.test` to publish a dataset. Every dev password equals its
username; the eight seeded users and what each one exists to prove are in
[the realm reference](https://spindoxlabs.github.io/ds/services/keycloak/).

For iterating on code, `task dev:restart` replaces most services with hot-reload host
processes. It is faster, but does **not** exercise the Dockerfiles or the compose
environment; use `docker:restart` to validate those.

```bash
task --list             # every command
```

---

## How it fits together

```
                    ┌──────────────────── identity-registry ────────────────────┐
                    │  trust anchor · did:web · STS · credentials · revocation   │
                    └───────────▲───────────────────────────────▲───────────────┘
                                │                               │
   ┌────────────────────────────┴──────┐         ┌──────────────┴────────────────┐
   │  PROVIDER participant             │         │  CONSUMER participant         │
   │                                   │  DSP    │                               │
   │   EDC connector  ◀────────────────┼─────────┼──▶  EDC connector             │
   │        ▲                          │         │          ▲                    │
   │   ds-connector ──▶ ds-provenance  │         │   ds-connector ──▶ provenance │
   │        ▲  control plane, PDP      │         │                               │
   │   dataset-api ─┘ "may I return    │         └───────────────────────────────┘
   │    (external)     these rows?"    │
   └───────────────────────────────────┘         federated-catalog · portal
```

Each unit has a page in [the docs](https://spindoxlabs.github.io/ds/services/connector/)
describing what it does, its interfaces and its constraints.

| | |
|---|---|
| `services/` | deployable units — connector, identity-registry, portal, provenance, federated-catalog, EDC extensions, gateway, realm |
| `libs/` | importable Python packages — governance/ODRL mapping, auth, EDC client, the e2e harness |
| `helm/` | Kubernetes charts and helmfile |
| `schemas/` | JSON Schema for the YAML shapes that cross a repository boundary |
| `docs/` | the published site |

---

## Reading further

| Looking for | Go to |
|---|---|
| What a data space must implement | [Blueprints](https://spindoxlabs.github.io/ds/blueprints/) — DSSC and CEEDS as citable requirements |
| What *this* data space decided | [Rulebook](https://spindoxlabs.github.io/ds/rulebook/) — each rule with its enforcement status |
| `governance.yaml` → ODRL offers | [Policies](https://spindoxlabs.github.io/ds/rulebook/policies/) |
| Consent, personal data, GDPR posture | [Personal data](https://spindoxlabs.github.io/ds/rulebook/personal-data/) |
| The exchange protocol in detail | [Data exchange](https://spindoxlabs.github.io/ds/rulebook/data-exchange/) |
| What the code currently does | [Services](https://spindoxlabs.github.io/ds/services/connector/) — one page per unit |
| Running and testing it | [Development](https://spindoxlabs.github.io/ds/development/running-the-stack/) · [Testing](https://spindoxlabs.github.io/ds/development/testing/) |
| Deploying it | [Deployment](https://spindoxlabs.github.io/ds/deployment/) |
| Shared file formats | [Schemas](https://spindoxlabs.github.io/ds/schemas/) |

Concepts are explained on the documentation site. This README and the per-unit `README.md`
files are entry points — what a unit is and how to run it — and link out rather than
duplicate, so that each mechanism has a single description.

---

## Status

Actively developed. The exchange, consent, identity and provenance paths run end to end and
are covered by end-to-end flows on every change, alongside unit and integration suites in CI.

Scope boundaries and known limitations are documented in [Scope and
deviations](https://spindoxlabs.github.io/ds/rulebook/scope-and-deviations/).

Dev fixtures use `example-org`, `grid-operator` and `*.dataspaces.localhost` throughout: no
real organisation, site or dataset appears in this repository, and none should.

## License

Copyright © 2025 Spindox Labs. Licensed under the [Apache License 2.0](LICENSE).
