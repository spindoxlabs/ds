"""The `/internal/dataplane/authorize` shape, as both ends must read it.

These are contract tests, not model tests. Each one pins a property some reader
of the decision would otherwise have to assume — and the defect this module
exists because of was exactly such an assumption: the connector emitted
`{handler, args, principals}`, the data-plane PEP read `{column, subject_ids}`,
and every *allow* carrying a filter died as an unhandled `KeyError`.
"""

import pytest
from pydantic import ValidationError

from ds.governance import (
    ALLOW,
    DENY,
    DIRECT_USER_MATCH,
    DataplaneDecision,
    DataplaneRowFilter,
    DatasetVerdict,
)
from ds.governance.models import RowFilterArgs

GATED = "datasets.silver.meters_15m"


def _allow(row_filter: dict | None = None) -> dict:
    return {
        "decision": ALLOW,
        "reason": None,
        "agreement_id": "agr-1",
        "transfer_id": "tp-1",
        "purpose": ["FlexibilityResearch"],
        "datasets": [
            {
                "dataset_id": GATED,
                "decision": ALLOW,
                "reason": None,
                "row_filter": row_filter,
            }
        ],
        "cache": {"ttl_seconds": 30},
    }


# ── the filter travels whole ──────────────────────────────────────────────────


def test_the_filter_carries_its_handler_not_just_a_column():
    """A column alone forces the PEP to assume a handler, and it assumed wrong.

    `rec_registry` resolves a member to their devices; `direct_user_match`
    matches the subject directly. Same column, different rows.
    """
    decision = DataplaneDecision.model_validate(
        _allow(
            {
                "handler": "rec_registry",
                "args": {"column": "device_id"},
                "principals": ["p1"],
            }
        )
    )
    row_filter = decision.datasets[0].row_filter
    assert row_filter is not None
    assert row_filter.handler == "rec_registry"
    assert row_filter.args["column"] == "device_id"
    assert row_filter.principals == ["p1"]


def test_the_old_shape_no_longer_parses():
    """`{column, subject_ids}` was the reading that produced the 500.

    It must fail loudly here rather than anywhere downstream of a narrowing.
    """
    with pytest.raises(ValidationError):
        DataplaneRowFilter.model_validate(
            {"column": "device_id", "subject_ids": ["did:web:example"]}
        )


def test_args_are_opaque_to_the_pdp():
    """A handler defines its own arguments and the PDP does not interpret them.

    `rec_registry` in the FIWARE adapter needs a `urn_template`. A model that
    admits only `column` drops it, and the handler then resolves an empty device
    set — which that adapter reads as *deny*.
    """
    row_filter = DataplaneRowFilter.model_validate(
        {
            "handler": "rec_registry",
            "args": {
                "column": "device_id",
                "urn_template": "urn:ngsi-ld:Device:{device_id}",
            },
            "principals": ["p1"],
        }
    )
    assert row_filter.args["urn_template"] == "urn:ngsi-ld:Device:{device_id}"


def test_governance_row_filter_args_keep_handler_specific_keys():
    """The same fact one layer earlier — governance parses the args, so it must
    not truncate them before the PDP ever puts them on the wire."""
    args = RowFilterArgs.model_validate(
        {"column": "device_id", "urn_template": "urn:ngsi-ld:Device:{device_id}"}
    )
    assert args.model_dump()["urn_template"] == "urn:ngsi-ld:Device:{device_id}"


# ── unknown fields are refused ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload, model",
    [
        (
            {
                "handler": DIRECT_USER_MATCH,
                "args": {},
                "principals": [],
                "invert": True,
            },
            DataplaneRowFilter,
        ),
        ({"dataset_id": GATED, "decision": ALLOW, "max_rows": 10}, DatasetVerdict),
    ],
)
def test_an_unrecognised_key_is_a_parse_failure(payload, model):
    """The dangerous drift is one-way.

    A PDP that adds a narrowing an older PEP ignores serves rows it should have
    withheld. `extra="forbid"` turns that into a denial instead. The cost —
    upgrading the connector ahead of a PEP stops the data plane — is the side we
    choose. Rulebook `CR-4`.
    """
    with pytest.raises(ValidationError):
        model.model_validate(payload)


# ── reading the decision ──────────────────────────────────────────────────────


def test_no_row_filter_on_an_allow_means_every_row():
    decision = DataplaneDecision.model_validate(_allow(None))
    assert decision.allowed
    assert decision.datasets[0].row_filter is None


def test_a_dataset_the_decision_never_mentions_is_not_an_allow():
    """A join asks about several datasets. Silence about one is not consent to
    serve it, so `verdict_for` reports the absence rather than a default."""
    decision = DataplaneDecision.model_validate(_allow(None))
    assert decision.verdict_for("datasets.gold.om_weather_features") is None
    assert decision.verdict_for(GATED) is not None


def test_the_envelope_and_the_verdicts_can_disagree_in_one_direction():
    """The envelope is the strictest of the verdicts — a deny envelope over an
    allow verdict is representable, and a PEP reading only the verdict is the
    reason the envelope must be checked first."""
    payload = _allow(None)
    payload["decision"] = DENY
    payload["reason"] = "transfer_inactive"
    decision = DataplaneDecision.model_validate(payload)
    assert not decision.allowed
    assert decision.datasets[0].allowed


def test_deny_and_allow_carry_the_same_keys():
    """A PEP should not branch on the envelope to know which fields it may read."""
    assert set(DataplaneDecision.model_fields) >= {
        "decision",
        "reason",
        "detail",
        "agreement_id",
        "transfer_id",
        "purpose",
        "datasets",
        "cache",
    }
