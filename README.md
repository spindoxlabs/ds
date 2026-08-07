# ds — a data space for energy communities

**Independent organisations publish data to each other under machine-readable contracts,
and the people the data describes decide what may be shared about them.**

`ds` is a working implementation of that second half. Contract-based data exchange between
organisations is well-trodden ground — the [Eclipse Dataspace
Components](https://projects.eclipse.org/projects/technology.edc) do it, and `ds` builds on
them rather than reinventing them. What is not well-trodden is what happens when the data
is *about households*: smart-meter readings, consumption profiles, flexibility events. Then
a contract between two companies is not enough, because a third party — the person the
data describes — has a say that neither signatory can give away.

So the consent of a data subject is a first-class object here. It is checked at contract
negotiation, again while a transfer is running, and once more on every query, and it
narrows results **row by row** before any data leaves the provider. Withdraw it and a
running transfer stops.

📖 **[Documentation](https://spindoxlabs.github.io/ds/)** — architecture, the rulebook, the
blueprint requirements, and the deployment reference.

---

## Who this is for

| If you are | What is here for you |
|---|---|
| **A DSO or grid operator** | A second provider in the dev fixture is a grid operator, deliberately: it shares its own network data and has no members, which is structurally different from a community and is the case a one-provider demo quietly assumes away |
| **An energy community or REC** | The consent plane — households granting and withdrawing use of their own data, per purpose, with the withdrawal reaching a running transfer |
| **A software company** | A platform, not a deployment. Domain specifics live in extension points: an ODRL profile, governance overlays, Keycloak client overlays. Apache-2.0 |
| **An EU research project** | Every blueprint requirement is rendered as a citable row with an enforcement status, and every deviation is written down. You can check the claims rather than take them |

---

## What actually runs

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

**Things worth knowing before you evaluate it:**

- The **policy decision point fails closed**. Stop the control plane and negotiation is
  refused rather than permitted — asserted against a stopped container on every full run,
  not argued in a document.
- **Withdrawing consent reaches a *running* transfer**, not merely the next one: the
  agreement is terminated and later queries refused. Neither blueprint asks for this; the
  rulebook records it as a rule participants can rely on anyway (`D-17`).
- The real data plane is an **external** service. `ds` addresses it over HTTP and calls it
  back for a per-query decision, so it does not own or copy your data.
- The **catalogue is advisory, never authority.** It is a crawler's projection; the
  provider's connector decides.

---

## Where it stands against the blueprints

This is the part usually written as a claim. Here it is written as a table you can audit.

`ds` implements the **[DSSC Blueprint](https://spindoxlabs.github.io/ds/blueprints/dssc/)**
reference architecture and specialises it for energy through
**[CEEDS](https://spindoxlabs.github.io/ds/blueprints/ceeds/)**. Both are rendered in the
docs as citable requirements — `DSSC-DEX-…`, `CEEDS-INT-…` — and the
[rulebook](https://spindoxlabs.github.io/ds/rulebook/) records what this data space decided
about each, **with an enforcement status per rule**:

| Status | Rules |
|---|--:|
| **Enforced** — code does it, and a test says so | 103 |
| **Declared** — a recorded decision rather than a mechanism | 21 |
| **Partly enforced** — stated with what is missing | 6 |
| **Not enforced** — written down rather than quietly dropped | 5 |
| | **135** |

**No conformance certification is claimed.** "DSSC-compliant" is not a badge this project
holds or has been assessed for, and a README that implied otherwise would be the kind of
claim this rulebook exists to make unnecessary. What is offered instead: every requirement
is named, every gap is either a recorded decision or a defect, and
**[Scope and deviations](https://spindoxlabs.github.io/ds/rulebook/scope-and-deviations/)**
lists what this platform deliberately does not do — value creation services, cross-data-space
federation, anonymisation, push and streaming transfers, and the largest CEEDS gap, payload
semantic models (CIM, SAREF4ENER and their neighbours), which is deferred to the deployment
rather than to nobody.

Where the two blueprints disagree — marketplaces are optional in DSSC and integral in CEEDS —
the choice is stated and the reasoning given. See
**[the comparison](https://spindoxlabs.github.io/ds/blueprints/comparison/)**.

---

## Quick start

**Prerequisites** — Docker with Compose v2, [Task](https://taskfile.dev) v3+,
[uv](https://docs.astral.sh/uv/), Node.js, and `tmux` for the hot-reload mode.
Full list: [Prerequisites](https://spindoxlabs.github.io/ds/deployment/prerequisites/).

```bash
task docker:restart     # everything in containers — exercises the images and compose env
task status             # what is running
task e2e:all            # prove it works, end to end
```

Then open **<http://portal.dataspaces.localhost>** and sign in as
`subject@example.test` (password `subject`) to see the consent plane from a household's
side, or `provider@example.test` to publish a dataset. Every dev password equals its
username; the eight seeded users and what each one exists to prove are in
[the realm reference](https://spindoxlabs.github.io/ds/services/keycloak/).

For iterating on code, `task dev:restart` replaces most services with hot-reload host
processes. It is faster and does **not** exercise the Dockerfiles or compose environment —
use `docker:restart` before trusting a result.

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

Each unit has a page in [the docs](https://spindoxlabs.github.io/ds/services/connector/);
each directory has an `AGENTS.md` with its boundaries and traps.

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

The documentation site is where concepts are explained. This README and the per-unit
`AGENTS.md` files are entry points: what a unit is, how to run it, what constrains it. They
link out rather than re-explain, because one mechanism described in three places is one
mechanism described three different ways.

---

## Status

Actively developed, and honest about the difference between working and finished. The
exchange, consent, identity and provenance paths run end to end and are covered by
end-to-end flows on every change. The gaps are enumerated rather than implied — start with
[Scope and deviations](https://spindoxlabs.github.io/ds/rulebook/scope-and-deviations/).

Dev fixtures use `example-org`, `grid-operator` and `*.dataspaces.localhost` throughout: no
real organisation, site or dataset appears in this repository, and none should.

## License

Copyright © 2025 Spindox Labs. Licensed under the [Apache License 2.0](LICENSE).
