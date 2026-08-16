# ADR-0004 — What is an ADR and what is a rulebook rule

**Date:** 2026-08-12
**Status:** accepted

## Context

Introducing `docs/decisions/` puts a second decision-shaped directory beside
`docs/rulebook/`, and without a boundary the two will collide immediately — both hold
statements of the form "this is how we do it, and here is why".

The collision is not cosmetic. `docs/rulebook/` is **measured**: every rule claims an
enforcement status, `libs/ds-conformance` checks that claim against the tests that name
the rule, and `docs/rulebook/status.md` reports any rule claiming enforcement that no test
evidences. A statement that lands in the rulebook and cannot be evidenced becomes a
reported defect. A statement that lands in `docs/decisions/` is measured by nothing.

Put an engineering decision in the rulebook and it pollutes the conformance report with
something no test can prove. Put a dataspace obligation in an ADR and it silently escapes
measurement. Both directions are worse than the status quo of having one directory.

## Decision

The boundary is **whether the statement has a blueprint referent**.

| | `docs/rulebook/` | `docs/decisions/` |
|---|---|---|
| Answers | what this dataspace does about a DSSC/CEEDS obligation | why this codebase is built the way it is |
| Has a blueprint row behind it | yes | no |
| Carries an enforcement status | yes | no |
| Evidenced by a test naming its identifier | yes | no |
| Measured by `task rulebook:status` | yes | never |
| Identifier | a rule id — `D-15`, `A-11` | `ADR-####` |
| Examples | consent must be checked per query; a subject DID must resolve | backend URLs use the host gateway; `data/` is the only writable root |

Two consequences of the test, stated so they are not re-argued:

- **If a statement could be given a rulebook rule id and a test that names it, it belongs
  in the rulebook**, even if it feels like an engineering matter. The rulebook is where
  things get measured, and measurement is the scarce property.
- **An ADR may record why a rule was written the way it was.** It links to the rule; it
  does not restate it, and it never claims an enforcement status.

An ADR is immutable once accepted. It is superseded by a later ADR that names it, never
edited to say something else.

## Consequences

- `docs/rulebook/status.md` stays a report about obligations, and its counts stay
  comparable across time.
- The rationale currently embedded in `AGENTS.md` prose, in `Taskfile.yml` comments and in
  the header blocks of `.github/workflows/*.yml` has a home that is neither a guide nor a
  rule. `AGENTS.md` keeps the constraint and points at the ADR.
- A borderline case will arrive — a decision with a blueprint referent that no test can
  reach. It goes in the rulebook, claiming *not enforced*, which is a fact the conformance
  report is designed to carry. An ADR would hide it.
- Both directories are published in the mkdocs site, so an external reader can see the
  obligations and the engineering reasoning without needing the repository.
