# ADR-0006 — The defect ledger owns its identifier namespace

**Date:** 2026-08-12
**Status:** superseded by [ADR-0012](ADR-0012-defects-are-issues.md)

This repository named its defects — `DID-11`, `E2E-01`, `GOV-19`, `TASK-10` and their
siblings — and cited those names from source, CI and published pages, while the file
defining them was untracked. A reader of a published page could not resolve one, and the
bare `GOV-` prefix sat one hyphen from the blueprint's `CEEDS-GOV-10`.

The ledger was given a committed home and ownership of its prefixes, which fixed the
citation and left the modelling wrong: a defect is an observation with a lifecycle, an
owner and a priority, and none of the artifacts here model that.

**The argument holds — an identifier must resolve.** Where it resolves to was the error.
The ledger is retired and the issue number is the identifier (ADR-0012).
