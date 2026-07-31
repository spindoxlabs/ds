"""The PEP half of `/internal/dataplane/authorize`.

This service is the reference implementation of the data-plane PEP — the real
celine `dataset-api` is written against the same contract — so what it does with
a decision is worth asserting even though it is a mock.

The suite exists because of one defect: the connector answered
`{handler, args, principals}` and this file read `row_filter["column"]`, so every
*allow* carrying a filter was an unhandled `KeyError` → 500. There was no test to
catch it, on either side of the seam. The shape now has one home
(`ds.governance.dataplane`) and both ends parse it.
"""

from __future__ import annotations

import pytest
from ds.governance import ALLOW, DENY, DIRECT_USER_MATCH, DataplaneRowFilter
from fastapi import HTTPException

from dataset_api_mock.main import _apply_row_filter

ROWS = [
    {"sub": "alice", "kwh": 0.42},
    {"sub": "alice", "kwh": 0.37},
    {"sub": "bob", "kwh": 0.55},
    {"sub": "carol", "kwh": 0.11},
]


def _filter(handler: str = DIRECT_USER_MATCH, **kwargs) -> DataplaneRowFilter:
    payload = {"handler": handler, "args": {"column": "sub"}, "principals": ["alice"]}
    payload.update(kwargs)
    return DataplaneRowFilter.model_validate(payload)


def test_direct_user_match_narrows_to_the_consenting_principals():
    kept = _apply_row_filter(ROWS, _filter(principals=["alice", "carol"]))
    assert [row["sub"] for row in kept] == ["alice", "alice", "carol"]


def test_a_handler_this_plane_cannot_run_withholds_every_row():
    """An *allow* carrying a filter says "these rows", not "all rows".

    `rec_registry` resolves a member to their devices against a registry this
    service does not have. Serving unfiltered because the instruction was not
    understood is the leak; refusing is the only reading that is not a guess.
    """
    with pytest.raises(HTTPException) as exc:
        _apply_row_filter(ROWS, _filter(handler="rec_registry"))
    assert exc.value.status_code == 403
    assert "rec_registry" in exc.value.detail


def test_a_filter_naming_no_column_withholds_every_row():
    with pytest.raises(HTTPException) as exc:
        _apply_row_filter(ROWS, _filter(args={}))
    assert exc.value.status_code == 403


def test_an_empty_principal_set_narrows_to_nothing():
    """Never to everything.

    ds denies before it sends one, so this is unreachable through the connector —
    which is exactly why it is worth pinning: the two readings of an empty list
    differ by the whole dataset, and the wrong one is silent.
    """
    assert _apply_row_filter(ROWS, _filter(principals=[])) == []


def test_the_old_reading_is_gone():
    """`{column, subject_ids}` no longer parses, so it cannot be read by accident."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DataplaneRowFilter.model_validate({"column": "sub", "subject_ids": ["alice"]})


def test_the_decision_vocabulary_comes_from_the_shared_library():
    """Not from string literals in this file, and not from the connector's."""
    assert (ALLOW, DENY) == ("allow", "deny")
    assert DIRECT_USER_MATCH == "direct_user_match"
