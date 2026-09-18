"""The deprecated spellings of the recipient, on the two surfaces that carry it.

`recipients.controller` meant the recipient, the subject's home organisation and
the GDPR Art. 4(7) controller at once, and only the first reading held in every
offer of a real four-hop chain
(`every-personal-dataset-asks-for-a-local-consent`, step 1). The field says what
it is now — the DSP consumer, ODRL 2.2's `odrl:recipient`, the DSSC data
recipient — and two things still have to read the old name:

- a **governance file**, which is a producer's artefact in another repository;
- `POST /consent/request`, whose body this connector does not own either.

`ConsentRequestCreate` does not forbid unknown fields, so dropping the old names
would have made an old caller's recipient *vanish* rather than 422 — the quietest
possible way to lose the dimension `D-14` says a wildcard must never cross. It is
an alias, and this is the test that keeps it working.
"""

from __future__ import annotations

import pytest

from connector.api.v1.consent import ConsentRequestCreate


def _body(**overrides) -> dict:
    payload = {
        "consumer_id": "did:web:third-party.dataspaces.localhost",
        "dataset_id": "datasets.silver.meters_15m",
        "subject_ids": ["did:web:rec.dataspaces.localhost:users:data-subject"],
        "purpose": ["EnergyCommunityOperation"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.rule("D-11")
def test_the_deprecated_controller_field_is_read_as_the_recipient():
    parsed = ConsentRequestCreate.model_validate(
        _body(controller="grid-operator", controller_role="operations")
    )
    assert parsed.recipient == "grid-operator"
    assert parsed.recipient_role == "operations"


@pytest.mark.rule("D-11")
def test_the_current_spelling_is_read():
    parsed = ConsentRequestCreate.model_validate(
        _body(recipient="grid-operator", recipient_role="operations")
    )
    assert parsed.recipient == "grid-operator"
    assert parsed.recipient_role == "operations"


def test_neither_spelling_leaves_the_recipient_unset_rather_than_failing():
    """A body naming no recipient is legitimate — a negotiated ask carries none.

    Pinned because the alias makes it easy to believe the field became required.
    """
    parsed = ConsentRequestCreate.model_validate(_body())
    assert parsed.recipient is None
    assert parsed.recipient_role is None
