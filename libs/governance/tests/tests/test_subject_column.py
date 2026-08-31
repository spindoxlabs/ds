"""GOV-05 · one subject column, one reader.

A dataset's subject column is read in two places that must never disagree:

- `models.subject_column(rule)` — what `connector/api/v1/internal.py:484` gives
  the data plane on every `/internal/dataplane/authorize` decision;
- `GovernanceMapper.to_asset_create` — what is published to EDC as
  `{prefix}:userFilterColumn`, and therefore what the catalogue says.

They resolved the two spellings in **opposite** orders. A rule declaring both
published one column and filtered on the other: the catalogue described a filter
this dataspace was not applying, and the data plane applied one it had not
described.

The tie-break is not ours to invent — `get_row_filter_specs` in the real celine
`dataset-api` appends the `row_filters` entries first and migrates the legacy
`userFilterColumn` in behind them, so **canonical leads**. The mapper already
agreed with that; the helper did not, which is the opposite of what the defect
row said.
"""

from __future__ import annotations

import pytest

from ds.governance import subject_column
from ds.governance.mapper import GovernanceMapper
from ds.governance.models import (
    GovernanceRuleV2,
    OdrlProfile,
    RowFilter,
)

CANONICAL = "device_id"
LEGACY = "user_id"


def profile() -> OdrlProfile:
    return OdrlProfile(prefix="ds", namespace="https://w3id.org/dataspaces/ns/")


def mapper() -> GovernanceMapper:
    return GovernanceMapper(
        participant_id="rec",
        base_url="http://172.17.0.1:30001",
        profile=profile(),
        participant_did="did:web:rec.dataspaces.localhost",
    )


def rule(**kwargs) -> GovernanceRuleV2:
    return GovernanceRuleV2(**kwargs)


def row_filter(column: str) -> RowFilter:
    return RowFilter(handler="direct_user_match", args={"column": column})


def published_column(r: GovernanceRuleV2) -> str | None:
    asset = mapper().to_asset_create("energy.meter_readings", r)
    return asset["properties"]["ds:userFilterColumn"]


# ── The two spellings, read alone ────────────────────────────────────────────


def test_canonical_spelling_alone():
    r = rule(row_filters=[row_filter(CANONICAL)])
    assert subject_column(r) == CANONICAL
    assert published_column(r) == CANONICAL


def test_legacy_spelling_alone_still_works():
    """Deployed governance files still use it, so it is not merely tolerated —
    dropping it would leave a correctly-configured dataset served unfiltered."""
    r = rule(user_filter_column=LEGACY)
    assert subject_column(r) == LEGACY
    assert published_column(r) == LEGACY


def test_neither_spelling_means_no_subject_column():
    r = rule()
    assert subject_column(r) is None
    assert published_column(r) is None


# ── Both declared: the case that was inconsistent ────────────────────────────


def test_canonical_wins_when_both_are_declared():
    """The real dataset-api's order, and now ours.

    Before `GOV-05`, `subject_column` returned `user_id` here while the asset
    published `device_id`.
    """
    r = rule(row_filters=[row_filter(CANONICAL)], user_filter_column=LEGACY)
    assert subject_column(r) == CANONICAL


def test_the_two_readers_agree_when_both_are_declared():
    """Agreement, asserted through the published asset rather than assumed.

    Worth being exact about what this can and cannot catch. The mapper now
    *calls* `subject_column`, so the two cannot disagree by construction — and
    that structural fix, not this assertion, is what closes the row. Reverting
    only the helper's precedence leaves this test green (both move together) and
    fails `test_canonical_wins_when_both_are_declared` instead, which is the
    correct division of labour: **this** test fails if someone re-introduces a
    second reader, that one fails if the direction is wrong.
    """
    r = rule(row_filters=[row_filter(CANONICAL)], user_filter_column=LEGACY)
    assert subject_column(r) == published_column(r)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"row_filters": [row_filter(CANONICAL)]},
        {"user_filter_column": LEGACY},
        {"row_filters": [row_filter(CANONICAL)], "user_filter_column": LEGACY},
        {"row_filters": [row_filter(CANONICAL), row_filter("other_col")]},
        {},
    ],
    ids=["canonical", "legacy", "both", "two-filters", "neither"],
)
def test_the_catalogue_never_describes_a_filter_the_pdp_does_not_apply(kwargs):
    """The generalised form: whatever governance says, the two must match.

    Stated this way it survives a third spelling being added — which is how the
    second one arrived.
    """
    r = rule(**kwargs)
    assert published_column(r) == subject_column(r)


# ── Shape tolerance, since fixtures build rules by hand ──────────────────────


def test_a_row_filter_whose_args_are_a_plain_dict_is_read():
    """Parsed YAML gives a model; a hand-built test fixture gives a dict. A
    helper that only handles one of them is how a fixture silently tests
    nothing."""
    r = GovernanceRuleV2.model_construct(
        row_filters=[type("F", (), {"args": {"column": CANONICAL}})()],
        user_filter_column=None,
    )
    assert subject_column(r) == CANONICAL


def test_a_row_filter_with_no_column_falls_through_to_the_legacy_field():
    """A malformed canonical entry must not shadow a usable legacy one — that
    would serve unfiltered rows for a dataset that declared a subject."""
    r = GovernanceRuleV2.model_construct(
        row_filters=[type("F", (), {"args": {}})()],
        user_filter_column=LEGACY,
    )
    assert subject_column(r) == LEGACY
