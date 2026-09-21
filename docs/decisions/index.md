# Decisions

Architecture decision records: **why a technical choice was made here**, when the reason
is not derivable from the code and would otherwise be re-litigated.

An ADR is not a rule. `docs/rulebook/` holds what this dataspace has decided to do about a
blueprint obligation — those rules are measured, each one claiming an enforcement status
that `task rulebook:status` checks against the tests that name it. An ADR has no blueprint
referent and nothing measures it. ADR-0004 states the boundary.

| ADR | Decision |
|---|---|
| [ADR-0001](ADR-0001-conformance-stays-with-the-rulebook.md) | Traceability stays with the rulebook and `ds-conformance` |
| [ADR-0002](ADR-0002-agent-material-is-not-committed.md) | Agent working material is not committed |
| [ADR-0003](ADR-0003-plans-hold-intent-work-holds-progress.md) | ~~Plans hold intent, work holds progress~~ — superseded by ADR-0002 |
| [ADR-0004](ADR-0004-decisions-versus-rulebook.md) | What is an ADR and what is a rulebook rule |
| [ADR-0005](ADR-0005-knowledge-mirrors-the-tree.md) | ~~Knowledge mirrors the repository tree~~ — superseded by ADR-0002 |
| [ADR-0006](ADR-0006-defect-ledger-owns-its-namespace.md) | ~~The defect ledger owns its identifier namespace~~ — superseded by ADR-0012 |
| [ADR-0007](ADR-0007-host-gateway-binding.md) | Backend URLs use the Docker host gateway |
| [ADR-0008](ADR-0008-data-is-the-only-writable-root.md) | `data/` is the only writable root |
| [ADR-0009](ADR-0009-enumerate-by-glob.md) | Iterate, never enumerate |
| [ADR-0010](ADR-0010-integration-layer-exists-for-the-database.md) | The integration layer exists because migrations run in no unit test |
| [ADR-0011](ADR-0011-ci-provisions-a-real-realm.md) | CI provisions a real Keycloak realm rather than mocking it |
| [ADR-0012](ADR-0012-defects-are-issues.md) | Defects are issues, not a repository artifact |
| [ADR-0013](ADR-0013-governance-shape-comes-from-celine-utils.md) | The governance shape comes from `celine.governance`, not a parallel implementation |
| [ADR-0014](ADR-0014-management-api-v5-and-the-organisation-actor.md) | The management API is v5beta behind OAuth2, and an organisation can act as itself |
| [ADR-0015](ADR-0015-a-collector-registers-consent-at-the-holder.md) | A collector registers consent at the holder |
| [ADR-0016](ADR-0016-access-policy-and-contract-policy-are-two-policies.md) | The access policy and the contract policy are two policies, and membership is a credential claim |
| [ADR-0017](ADR-0017-the-sync-reconciles-and-says-so.md) | The provider sync reconciles, and its answer agrees with what happened — *amended 2026-09-20: the withdrawal is recorded, as `CatalogueWithdrawn`* |
| [ADR-0018](ADR-0018-the-edc-schema-migrates-through-edcs-own-bootstrapper.md) | The EDC schema migrates through EDC's own bootstrapper |
| [ADR-0019](ADR-0019-a-collector-says-why-it-withdrew.md) | A collector says why it withdrew |
| [ADR-0020](ADR-0020-each-withdrawal-is-its-own-record.md) | Each withdrawal is its own record, and the member's is the one presented |

ADR-0007 and ADR-0008 were extracted from prose in the root agent guide; ADR-0009 to
ADR-0011 from comment blocks in `Taskfile.yml` and `.github/workflows/`. Where the rule
has a place that enforces it, it stays there and only the reasoning moves here.
