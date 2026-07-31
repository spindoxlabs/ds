# ds-connector

Python control plane beside an EDC runtime. One codebase, **two instances** —
`CONNECTOR_ROLE` selects the EDC client and which routers mount.

30001 provider / 31001 consumer (debug 30901 / 31901). PostgreSQL.

## References

| | |
|---|---|
| Requirements | [DSSC · Access & Usage Policies Enforcement](../../docs/blueprints/dssc/data-sovereignty-and-trust/access-and-usage-policies-enforcement.md) · [DSSC · Data Exchange](../../docs/blueprints/dssc/data-interoperability/data-exchange.md) · [DSSC · Cross-cutting (personal data)](../../docs/blueprints/dssc/cross-cutting.md) |
| Rules | [Rulebook · Policies](../../docs/rulebook/policies.md) · [Rulebook · Personal data](../../docs/rulebook/personal-data.md) |
| Code as committed | [docs/services/connector.md](../../docs/services/connector.md) |

## Role

| Surface | Responsibility |
|---|---|
| `POST /provider/sync` | Publishes `governance.yaml` into EDC as assets, policies, contract definitions |
| `/internal/*` | The PDP — answers the EDC constraint functions and the data-plane PEP |
| `/consent/*` | The consent registry |
| `/consumer/*` | Drives the consumer side of DSP: catalogue → negotiate → transfer → EDR |
| `/webhooks/*` | Records EDC negotiation and transfer lifecycle |
| `/ns/*` | Public vocabularies — ODRL profile, sharing offers |

Every act emits a PROV-O event through `services/prov_bridge.py`.

## Where to work

| Task | Start at |
|---|---|
| New endpoint | `api/v1/<group>.py`, register in `main.py`, guard per root AGENTS.md |
| Auth guard / per-owner scoping | `dependencies.py` — read [the owner perimeter](#the-owner-perimeter) first |
| Consent behaviour | `services/consent_service.py` |
| What a consent write may say | `services/consent_vocabulary.py` — the single validation point; raises 422 |
| Covered processor vs independent controller | `services/circle.py` |
| Governance → ODRL | `libs/governance/.../mapper.py` — shared lib, not here |
| EDC calls | `libs/ds-edc/.../client.py` — shared lib. Never call EDC from a route |
| Provenance emission | `services/prov_bridge.py` |
| Schema change | `db/models.py`, then `task db:revision MESSAGE=...` |

The **rules** of the consent model — purposes, controller roles, the scoped wildcard,
legal-basis evidence, what fails closed — are in `docs/rulebook/personal-data.md`. Change
them there and here in the same commit.

## The owner perimeter

A participant may host datasets for several owners, and `connector.provider.write` says
nothing about *which*. `require_provider_write_own` guards the provider deletes; cases and
reasoning are in `tests/test_provider_owner_perimeter.py`.

Three things to get right if you write a similar guard:

- **`_asset_owner` matches the local name, not a prefix.** EDC JSON-LD-compacts to the
  active profile's prefix (`dsp-policy:owner`), not `ds:owner`. The first version read the
  wrong key, found no owner, and allowed every write — with six passing unit tests, because
  they asserted against a key the tests invented. **A guard reading a field written
  elsewhere needs one end-to-end assertion against the real writer.**
- **`_canonical_owner` resolves the claim's alias through the owners registry**, so
  `Owner.aliases[]` is honoured.
- **Ask the per-organisation question** (`Principal.grants_in`), not "member of X *and*
  holds the permission somewhere" — the latter admits a viewer in A who is admin in B.

Policies and contracts carry no owner in EDC, so their deletes resolve it through governance
(`owner_by_edc_id()`). `POST /provider/sync` is deliberately participant-wide — it
republishes the whole file, so there is no owner to scope it to. Per-owner sync is a
governance-model change; **do not fake it with a guard.**

## Governance files

`governance/governance.yaml` and `governance/sharing-offers.yaml`, each with a
`<name>.yaml` overlay (`*.local.yaml` gitignored). Producer-contributed offers land in
`governance/sharing-offers.d/` as a **union**: duplicate ids raise, no file has precedence,
the deployment overlay applies last. Field meanings and the mandatory set:
`docs/rulebook/catalogue-and-metadata.md`.

**The image and `governance.yaml` travel together.** The file is mounted, the parser is not
— editing governance without rebuilding the connector can leave the running code unable to
read the new shape. That has published a policy with no purpose constraint, so every
negotiation parked forever on a question nobody could answer. No error, no log.

## Conventions

- Route handlers stay thin: validate, call a service, return
- `tenacity` for EDC polling retries
- Any model recording **evidence** is `extra="forbid"`. Pydantic's default drops an unknown
  key and answers 200 — leaving the caller holding written proof of something never stored

## Testing

`task -d services/connector test` · `lint` · `db:migrate`. pytest-asyncio, respx, SQLite
in-memory.

`tests/conftest.py` points the consent vocabulary at `tests/fixtures/` before settings are
read and clears the caches per test, so the suite asserts against a stable vocabulary rather
than the dev catalogue. `tests/__init__.py` provides `make_headers` (service token),
`make_user_headers` (groups) and `make_vc_headers` (the `X-Subject-Id` + `X-User-VC`
mechanism the `/consent/*` routes actually use).

Known-failing tests are tracked in `.agents/defect-per-service.md`, not here.
