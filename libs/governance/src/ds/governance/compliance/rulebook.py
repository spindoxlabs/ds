"""Which rulebook rule each check enforces — `C-13`, `DSSC-DSO-12`.

`C-13` is *metadata is checked for compliance with **this rulebook***, and it sat
at *partly enforced* with the prerequisite built and the direction missing: the
rulebook was projected to `docs/rulebook/rules.json` (`GOV-18`), and nothing in
the gate referred to it. Every check carried its own private copy of the rule it
came from — in a docstring, at best.

**The framing the plan had was wrong, and it is worth saying why.** It asked
*which rules are mechanically checkable against metadata*, as if a set had to be
chosen. Enumerating all 35 rules on the two metadata pages settles that: most are
**already enforced by a named check of their own** (`C-9`, `C-10`, `C-11`,
`C-12`, `C-14`, `M-1`–`M-4`, `M-7`, `M-9`, `M-10`), the rest are runtime or
authorisation properties no validator can see (`C-15`–`C-20`, `M-8`, `M-11`) or
process declarations no validator can test (`C-2`, `M-5`, `M-6`, `M-12`–`M-14`).

So the gap was never coverage. It was **attribution**: a finding said which
*check* failed and never which *rule* that check exists to keep, so the rulebook
was descriptive where it should have been load-bearing. This module is the one
place that mapping lives, and `tests/tests/test_rulebook_citations.py` asserts
every id in it resolves in the projection — which is what stops this becoming a
third copy of the vocabulary.

**A check with no rule is allowed, and is not an oversight.** Several checks
enforce a *model* invariant rather than a rulebook decision (`governance-file`,
`policy-contract-id-collision`). Mapping them to a rule for symmetry's sake would
be inventing a citation, which is the failure mode this whole exercise is meant
to remove.
"""
from __future__ import annotations

#: check name → the rulebook rule ids it enforces.
#:
#: Ids are `docs/rulebook/*.md` rule ids as the projection carries them, and the
#: test in this package's suite fails on any that does not resolve. Adding a
#: check without a rule is fine; adding one with a **wrong** rule is not, which
#: is the asymmetry worth having.
CHECK_RULES: dict[str, tuple[str, ...]] = {
    # ── Catalogue and metadata ───────────────────────────────────────────────
    "dcat-ap": ("C-12", "C-14"),
    "data-address": ("C-9",),
    "semantic-model": ("M-4", "M-7"),
    "declared-not-enforced": ("A-9",),
    # ── Policies ─────────────────────────────────────────────────────────────
    "access-level": ("C-5",),
    "classification": ("D-1",),
    "key-policy": ("C-9",),
    # ── Personal data ────────────────────────────────────────────────────────
    "consent-coherence": ("C-10", "D-11"),
    "retention": ("D-12",),
    "validity-window": ("A-9",),
    # ── Owners and participants ──────────────────────────────────────────────
    "owner-declared": ("C-16",),
    "owner-resolvable": ("C-16",),
    "owner-participant": ("C-15",),
    # ── The consent vocabulary ───────────────────────────────────────────────
    "purpose-declared": ("D-7", "C-11"),
    "purpose-hierarchy": ("D-8", "M-13"),
    "purpose-mapping": ("D-8", "M-13"),
    "purpose-labels": ("D-13",),
    "purpose-iri-shape": ("M-7",),
    "offer-purpose": ("D-10",),
    "offer-controller": ("D-11", "D-11a"),
    "offer-legal-basis": ("D-4", "D-6"),
    "offer-consent-required": ("C-10",),
    "offer-dataset-purpose": ("D-7",),
    "offer-datasets": ("C-10",),
    "offer-durations": ("D-12",),
    "offer-codes": ("D-13",),
    "offer-hash-stability": ("D-13",),
    "offer-duplicate": ("D-13",),
}


def rules_for(check: str) -> tuple[str, ...]:
    """The rule ids *check* enforces, or empty when it enforces a model invariant."""
    return CHECK_RULES.get(check, ())


def cite(check: str) -> str:
    """``"dcat-ap (C-12, C-14)"`` — the form a finding carries.

    The check name stays first and unchanged: it is what a reader greps for and
    what every existing test asserts on. The citation is an addition, not a
    rename.
    """
    rules = rules_for(check)
    return f"{check} ({', '.join(rules)})" if rules else check
