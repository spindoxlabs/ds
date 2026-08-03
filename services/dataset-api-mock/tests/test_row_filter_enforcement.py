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

from dataset_api_mock.main import REC_MEMBERS, REC_REGISTRY, _apply_row_filter

# A handler no PEP anywhere implements. It stands for "an instruction this plane
# was not built to follow" — `rec_registry` used to play that part and no longer
# can, which is the point of this pass.
UNKNOWN_HANDLER = "postgres_row_security"

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

    Serving unfiltered because the instruction was not understood is the leak;
    refusing is the only reading that is not a guess.
    """
    with pytest.raises(HTTPException) as exc:
        _apply_row_filter(ROWS, _filter(handler=UNKNOWN_HANDLER))
    assert exc.value.status_code == 403
    assert UNKNOWN_HANDLER in exc.value.detail


DEVICE_ROWS = [
    {"device_id": "ds-e2e-METER-0001", "kwh": 0.42},
    {"device_id": "ds-e2e-METER-0002", "kwh": 0.55},
    {"device_id": "ds-e2e-METER-9999", "kwh": 9.99},
]


def _rec_filter(principals: list[str]) -> DataplaneRowFilter:
    return DataplaneRowFilter.model_validate(
        {"handler": REC_REGISTRY, "args": {"column": "device_id"}, "principals": principals}
    )


def test_rec_registry_resolves_a_member_to_their_own_devices():
    """The handler is what maps a person to values in the column.

    ds names `subject@example.test` — a Keycloak username, the identifier the
    receiving system keys on — and never the meter. Resolving that to
    `ds-e2e-METER-0001` is this plane's job, and it is the hop that used to be
    missing entirely.
    """
    kept = _rec_filter(["subject@example.test"])
    assert [row["device_id"] for row in _apply_row_filter(DEVICE_ROWS, kept)] == [
        "ds-e2e-METER-0001"
    ]


def test_rec_registry_never_serves_the_unowned_device():
    """`ds-e2e-METER-9999` belongs to no member: the negative control.

    A run that returns it has lost the filter — and a lost filter that returns
    *more* rows looks like a larger result set, not like a failure, which is why
    the fixture carries a row nobody may ever see.
    """
    everyone = list(REC_MEMBERS)
    served = _apply_row_filter(DEVICE_ROWS, _rec_filter(everyone))
    assert "ds-e2e-METER-9999" not in {row["device_id"] for row in served}
    assert len(served) == 2


def test_a_principal_the_registry_cannot_resolve_narrows_to_nothing():
    """Not to everything.

    An unknown member owns no devices. Reading "resolved to no values" as "no
    filter" is the same mistake as reading an empty principal set that way, one
    layer further in.
    """
    assert _apply_row_filter(DEVICE_ROWS, _rec_filter(["nobody@example.test"])) == []


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


def test_handler_names_are_this_planes_own():
    """`rec_registry` is deliberately *not* in `ds.governance`.

    ds passes the handler through from `governance.yaml` and never interprets it
    — `DataplaneRowFilter` says as much where it declares `args` open. Which
    registry resolves a principal to column values is a property of the data
    plane holding the data, so a control-plane library enumerating handlers would
    invite ds to reason about one it cannot run.

    The two ends still have to agree, and they agree through `governance.yaml` —
    checked against the file itself in `test_dataset_fixtures.py`, which is a
    stronger check than a shared constant because it is the declaration the
    connector actually reads.
    """
    import ds.governance as governance

    assert not hasattr(governance, "REC_REGISTRY")
    assert REC_REGISTRY == "rec_registry"
