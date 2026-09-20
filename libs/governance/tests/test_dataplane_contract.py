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


# ── typed keys travel beside the principals ───────────────────────────────────
#
# Plan `a-collector-registers-consent-at-the-holder`: the collector sends the
# subject's data keys with the consent, and the filter carries them so the
# holder's data plane needs no call back to the collector.


def test_the_filter_carries_typed_keys_beside_the_principals():
    from ds.governance import DataplaneDecision as Decision

    decision = Decision.model_validate(
        _allow(
            {
                "handler": "subject_key_match",
                "args": {"column": "pod", "key_type": "pod"},
                "principals": [],
                "keys": ["pod:EX000E00000001", "pod:EX000E00000002"],
            }
        )
    )
    row_filter = decision.verdict_for(GATED).row_filter
    assert row_filter.keys == ["pod:EX000E00000001", "pod:EX000E00000002"]
    assert row_filter.principals == []


def test_keys_default_to_an_empty_allow_list():
    assert DataplaneRowFilter(handler="rec_registry").keys == []


def test_a_decision_with_keys_is_refused_by_a_reader_without_them():
    """The one-way drift rule, applied to the new field: an older PEP must deny."""
    from pydantic import BaseModel, ConfigDict

    class OldRowFilter(BaseModel):
        model_config = ConfigDict(extra="forbid")
        handler: str
        args: dict = {}
        principals: list[str] = []

    payload = DataplaneRowFilter(
        handler="subject_key_match", keys=["pod:EX000E00000001"]
    ).model_dump()
    with pytest.raises(ValidationError):
        OldRowFilter.model_validate(payload)


# ── the subject DIDs travel beside the principals ─────────────────────────────
#
# Plan `a-write-scope-reads-the-whole-store`, finding 2: the PEP echoes the row
# filter's `principals` into `POST /internal/audit/query`, and `principals` are
# registry-native — in a realm where the username is the email, a list of
# addresses. 22 of them reached `QueryExecuted.authorized_subject_ids` in one
# measured run. The filter needs the usernames; the record needs the DIDs; so
# the decision carries both.

SUBJECT_A = "did:web:rec.example.org:users:ex-00001"
SUBJECT_B = "did:web:rec.example.org:users:ex-00002"


def test_the_filter_carries_the_subject_dids_beside_the_principals():
    """Both lists, distinct, neither replacing the other.

    `principals` is what the handler matches on; `subject_dids` is what the PEP
    is permitted to report. Collapsing them either way breaks one of the two —
    a DID matches no column, and an address belongs in no provenance event.
    """
    decision = DataplaneDecision.model_validate(
        _allow(
            {
                "handler": DIRECT_USER_MATCH,
                "args": {"column": "owner"},
                "principals": ["someone@example.org"],
                "subject_dids": [SUBJECT_A],
            }
        )
    )
    row_filter = decision.verdict_for(GATED).row_filter
    assert row_filter.principals == ["someone@example.org"]
    assert row_filter.subject_dids == [SUBJECT_A]


def test_subject_dids_default_to_an_empty_list():
    assert DataplaneRowFilter(handler=DIRECT_USER_MATCH).subject_dids == []


def test_a_pdp_that_sends_no_subject_dids_still_parses():
    """**The skew test.** A newer PEP against an older PDP must keep serving.

    This is the half `extra="forbid"` does not cover, and a required field would
    have broken it. `subject_dids` narrows nothing — it never reaches a
    predicate — so its absence can only thin an audit record, never widen a
    disclosure. If this raised, the only safe deployment order would be "both at
    once", which is not an order.
    """
    row_filter = (
        DataplaneDecision.model_validate(
            _allow(
                {
                    "handler": DIRECT_USER_MATCH,
                    "args": {"column": "owner"},
                    "principals": ["someone@example.org"],
                }
            )
        )
        .verdict_for(GATED)
        .row_filter
    )

    assert row_filter.subject_dids == []
    assert row_filter.principals == ["someone@example.org"]


def test_a_decision_with_subject_dids_is_refused_by_a_reader_without_them():
    """**The other half of the skew**, and the one that takes a deployment down.

    A PEP that predates the field refuses the whole decision and answers 502.
    That is `extra="forbid"` working as designed, and it is why the data plane
    is rebuilt *before* the connector, never after.
    """
    from pydantic import BaseModel, ConfigDict

    class OldRowFilter(BaseModel):
        model_config = ConfigDict(extra="forbid")
        handler: str
        args: dict = {}
        principals: list[str] = []
        keys: list[str] = []

    payload = DataplaneRowFilter(
        handler=DIRECT_USER_MATCH, subject_dids=[SUBJECT_A]
    ).model_dump()
    with pytest.raises(ValidationError):
        OldRowFilter.model_validate(payload)


def test_the_two_lists_are_not_positionally_paired():
    """The DIDs are sorted; the principals keep the order consent resolved in.

    A shared index would hand every reader of the decision a DID-to-address
    mapping it was never given, which is the correlation the split exists to
    avoid.
    """
    row_filter = DataplaneRowFilter(
        handler=DIRECT_USER_MATCH,
        principals=["b@example.org", "a@example.org"],
        subject_dids=sorted([SUBJECT_B, SUBJECT_A]),
    )
    assert row_filter.subject_dids == [SUBJECT_A, SUBJECT_B]
    assert row_filter.principals == ["b@example.org", "a@example.org"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("pod:EX000E00000001", ("pod", "EX000E00000001")),
        ("meter-id:a:b", ("meter-id", "a:b")),
    ],
)
def test_a_typed_key_splits_at_the_first_colon(key, expected):
    from ds.governance.dataplane import split_key

    assert split_key(key) == expected


@pytest.mark.parametrize("key", ["", "pod", ":x", "POD:x", "pod:", "pod:has space"])
def test_a_malformed_key_is_refused(key):
    from ds.governance.dataplane import split_key

    with pytest.raises(ValueError):
        split_key(key)


def test_values_of_one_type_ignore_the_others_and_the_malformed():
    from ds.governance.dataplane import values_of_type

    assert values_of_type(
        ["pod:A", "meter:B", "junk", "pod:C"], "pod"
    ) == {"A", "C"}
