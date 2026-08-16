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
| [ADR-0002](ADR-0002-agents-directory-is-committed.md) | `.agents/` is committed; only `work/` is not |
| [ADR-0003](ADR-0003-plans-hold-intent-work-holds-progress.md) | Plans hold intent, `work/` holds progress |
| [ADR-0004](ADR-0004-decisions-versus-rulebook.md) | What is an ADR and what is a rulebook rule |
| [ADR-0005](ADR-0005-knowledge-mirrors-the-tree.md) | Knowledge mirrors the repository tree |
| [ADR-0006](ADR-0006-defect-ledger-owns-its-namespace.md) | ~~The defect ledger owns its identifier namespace~~ — superseded by ADR-0012 |
| [ADR-0007](ADR-0007-host-gateway-binding.md) | Backend URLs use the Docker host gateway |
| [ADR-0008](ADR-0008-data-is-the-only-writable-root.md) | `data/` is the only writable root |
| [ADR-0009](ADR-0009-enumerate-by-glob.md) | Iterate, never enumerate |
| [ADR-0010](ADR-0010-integration-layer-exists-for-the-database.md) | The integration layer exists because migrations run in no unit test |
| [ADR-0011](ADR-0011-ci-provisions-a-real-realm.md) | CI provisions a real Keycloak realm rather than mocking it |
| [ADR-0012](ADR-0012-defects-are-issues.md) | Defects are issues, not a repository artifact |

ADR-0007 and ADR-0008 were extracted from prose in `AGENTS.md`; ADR-0009 to ADR-0011 from
comment blocks in `Taskfile.yml` and `.github/workflows/`. In each case the rule stays
where it was and only the reasoning moves here.
