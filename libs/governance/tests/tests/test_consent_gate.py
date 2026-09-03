"""The consent gate — one predicate, and what asserted it.

[#21](https://github.com/spindoxlabs/ds/issues/21). `requires_consent` ORs four
signals, so a dataset's protection can rest on exactly one of them, and losing
that one is silent and looks like tidying. Two things are pinned here:

1. **The two spellings agree.** `ds.governance.mapper.requires_consent` and
   `connector.services.consent_vocabulary.requires_consent` were byte-identical
   copies held in step by nothing. The arrangement has already failed once —
   between the mapper and a since-deleted `matrix.py`, which differed by the `pii`
   clause, so a `pii` dataset with no filter was *reported gated and published
   ungated*. The connector's copy cannot be imported from here, so what is
   asserted is that the mapper's spelling **is** the one in `consent.py` rather
   than a second implementation of it.
2. **The gate names its signals.** The boolean was always knowable; which
   declaration answered was not, and that is the half a decision could not record.
"""

from __future__ import annotations

import pytest

from ds.governance import requires_consent as exported_requires_consent
from ds.governance.consent import CONSENT_SIGNALS, ConsentGate, consent_gate
from ds.governance.mapper import requires_consent as mapper_requires_consent
from ds.governance.models import (
    DataspaceSpec,
    GovernanceRuleV2,
    RowFilter,
    RowFilterArgs,
)


def _rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


def _filters() -> list[RowFilter]:
    return [RowFilter(handler="subject", args=RowFilterArgs(column="device_id"))]


# ── one predicate, not three ──────────────────────────────────────


@pytest.mark.rule("D-3a")
def test_the_mapper_spelling_is_the_same_object_not_a_second_copy():
    """Identity, not equality of behaviour on a sample. A copy that agrees on
    every case in this file is exactly what the two deleted implementations were,
    and the sample is what let them drift on the case nobody wrote down."""
    from ds.governance import consent

    assert mapper_requires_consent is consent.requires_consent
    assert exported_requires_consent is consent.requires_consent


# ── the four signals ──────────────────────────────────────────────


@pytest.mark.rule("D-3a")
@pytest.mark.parametrize(
    "rule,expected",
    [
        (_rule(), ()),
        (
            _rule(dataspace=DataspaceSpec(consent_required=True)),
            ("dataspace.consent_required",),
        ),
        (_rule(user_filter_column="subject_did"), ("user_filter_column",)),
        (_rule(row_filters=_filters()), ("row_filters",)),
        (_rule(classification="pii"), ("classification: pii",)),
    ],
    ids=["plain", "declared", "user-filter", "row-filter", "pii"],
)
def test_each_signal_alone_gates_and_names_itself(rule, expected):
    gate = consent_gate(rule)

    assert gate.signals == expected
    assert gate.gated is bool(expected)
    assert bool(gate) is bool(expected)
    assert requires_consent_agrees(rule, bool(expected))


def requires_consent_agrees(rule, expected: bool) -> bool:
    return mapper_requires_consent(rule) is expected


@pytest.mark.rule("D-3a")
def test_every_signal_is_collected_not_short_circuited():
    """A dataset gated by four declarations and one gated by a single
    `row_filters` are the same boolean and very different files: the first
    survives one of them being deleted, and the second is the deployment #21
    measured — fifteen personal datasets in `celine-pipelines`, gated by
    `row_filters` and nothing else."""
    gate = consent_gate(
        _rule(
            classification="pii",
            user_filter_column="subject_did",
            row_filters=_filters(),
            dataspace=DataspaceSpec(consent_required=True),
        )
    )

    assert gate.signals == CONSENT_SIGNALS
    assert len(gate.signals) == 4


@pytest.mark.rule("D-3a")
def test_the_signal_names_are_the_files_own_spelling():
    """The reader who needs this is looking at a governance file, not at the
    predicate, so the names have to be greppable in a YAML."""
    assert CONSENT_SIGNALS == (
        "dataspace.consent_required",
        "user_filter_column",
        "row_filters",
        "classification: pii",
    )


# ── the reason, which is what a log or a verdict carries ──────────


def test_the_reason_names_what_gated_it():
    gate = consent_gate(_rule(row_filters=_filters(), classification="pii"))

    assert gate.reason == "consent-gated by row_filters, classification: pii"


def test_an_ungated_dataset_says_so_rather_than_saying_nothing():
    """A blank reason reads as *missing* wherever this lands."""
    assert ConsentGate().reason == "not consent-gated"
    assert consent_gate(_rule()).reason == "not consent-gated"
