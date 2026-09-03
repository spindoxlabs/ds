"""The consent gate — whether a dataset's rows are gated on a subject's consent.

**One predicate, and it had three implementations.**
[#21](https://github.com/spindoxlabs/ds/issues/21). The rule is load-bearing in three
places — the ODRL offer on the wire (`mapper._build_permission`), the PDP verdict at
`POST /internal/dataplane/authorize`, and the compliance report — and it was held in step
by two functions happening to be typed the same way. That is not a mechanism. It has
already failed once: `mapper.py` and a since-deleted `matrix.py` differed by the `pii`
clause, so a `pii` dataset with no filter and no `consent.required` was **reported gated
and published ungated**, the divergence pointing at the auditor rather than at the wire.

**Four signals, ORed, and any one alone gates the dataset.** That is what the code has
always done; what is new here is that it is written down once and says *which* signal
answered. Measured across `celine-eu/celine-pipelines` on 2026-09-02: all 20 `rec`-owned
gold datasets were `classification: green` with `dataspace.consent_required` unset, and
fifteen declared `row_filters` on `device_id` — so **one arm of the OR was gating every
personal dataset in the deployment**, and it is the arm most likely to be touched by a
refactor of the data model rather than of the governance. Deleting `row_filters` from such
a dataset un-gates it silently, and the file looks *cleaner* afterwards.

`compliance.checks.check_consent_coherence` is the other half of the answer: it now errors
when the filters are present and neither `consent_required` nor `pii` is, so a file cannot
rest its whole protection on the arm a refactor reaches for without saying so.

**Why here, and not in `celine.governance`.** `ADR-0013` puts the *shape* of
`governance.yaml` upstream and the *use* here. Nothing upstream models a consent gate at
all — it has the `consent_required` field, its OR-merge rule and its facet key, and no
predicate. The gate is what ds's PDP does with the field, which is ds's concern and nobody
else's. `celine.governance.exposure` is the same split seen from the other side: upstream
owns `expose` because upstream's data plane refuses on it.

**Why its own module, and not `mapper.py` where it lived.** The mapper stopped being its
only reader when `services/connector` grew a copy. A predicate three components depend on
is not a mapper detail, and leaving it there is what made the second copy look reasonable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import GovernanceRuleV2

#: The four declarations, in the order they are reported, spelled as a governance
#: file spells them. The reader who needs a `ConsentGate` is looking at a YAML, not
#: at this module, so `dataspace.consent_required` rather than
#: `rule.dataspace.consent_required` and `classification: pii` rather than `pii`.
CONSENT_SIGNALS = (
    "dataspace.consent_required",
    "user_filter_column",
    "row_filters",
    "classification: pii",
)


@dataclass(frozen=True, slots=True)
class ConsentGate:
    """Whether a dataset is consent-gated, and **which declarations said so**.

    The set, not just the boolean, because the boolean is the half that was already
    knowable. `#21`'s second direction is that a decision should be able to say which
    declaration gated it: at the point of use the reason was invisible, and afterwards
    it was unrecoverable — a verdict recorded *deny, no consent* said nothing about
    whether the dataset was gated by a producer's explicit `consent_required` or by a
    `row_filters` block added for an unrelated reason.

    Empty `signals` is the ungated case. There is no separate flag for it: a gate with
    no signal asserting it is exactly what "not gated" means, and a second field
    agreeing with the first is the shape this whole module removes.
    """

    signals: tuple[str, ...] = ()

    @property
    def gated(self) -> bool:
        return bool(self.signals)

    def __bool__(self) -> bool:
        """So `if consent_gate(rule):` reads as the predicate it replaced."""
        return self.gated

    @property
    def reason(self) -> str:
        """One line naming what gated it, for a log or a verdict.

        ``"not consent-gated"`` when nothing did — a phrase rather than an empty
        string, because this lands in messages where a blank reads as *missing*.
        """
        if not self.signals:
            return "not consent-gated"
        return "consent-gated by " + ", ".join(self.signals)


def consent_gate(rule: GovernanceRuleV2) -> ConsentGate:
    """Resolve the gate, naming every declaration that asserts it.

    Every signal is collected rather than short-circuiting on the first. A dataset
    gated by three declarations and a dataset gated by one are the same boolean and
    very different files: the first survives one of them being deleted, and the
    second is the deployment measured in `#21`.

    `user_filter_column` is read directly here, and that is the one place it is
    right to. Elsewhere the rule is *never read it directly, call `subject_column`*
    (`GOV-05`), because the two spellings must resolve to one column and the
    canonical one has to win. This asks a different question — *did the producer
    declare per-subject access control at all?* — and for that the legacy spelling
    is its own answer, distinct from `row_filters`, and reporting which of the two
    was used is the point.
    """
    signals = tuple(
        name
        for name, asserted in zip(
            CONSENT_SIGNALS,
            (
                rule.dataspace.consent_required,
                rule.user_filter_column,
                rule.row_filters,
                rule.classification == "pii",
            ),
            strict=True,
        )
        if asserted
    )
    return ConsentGate(signals)


def requires_consent(rule: GovernanceRuleV2) -> bool:
    """Whether this dataset may only be accessed with the subject's consent.

    The boolean face of :func:`consent_gate`, kept because it is
    `ds.governance`'s published surface and because most callers genuinely only
    need the bit. Reach for `consent_gate` where the *reason* is going into a log,
    a verdict or a message.

    `classification: pii` is one of the four, and it is the rulebook's own switch:
    *"`classification: pii` on a dataset is the switch. A dataset carrying that
    classification is subject to everything on this page"*
    (Rulebook · Personal data §1). A producer that classifies a dataset `pii` has
    declared it personal data; publishing it without a consent term would say the
    opposite on the wire.

    A `pii` dataset with no row filter stays a **separate** defect:
    `check_consent_coherence` warns *"classified 'pii' but declares no row-level
    filtering"*, because a gate no column can evaluate per subject is a gate in
    name. Gating it here does not fix that; it stops the offer under-claiming while
    the warning names what is missing.
    """
    return consent_gate(rule).gated
