"""EDCL-09 and EDCL-06 · what this library offers, and what it stopped offering.

EDCL-09 removed three things that read as handled cases and were not:
`get_contract_negotiation_agreement` (a second name for `get_negotiation`),
`query_agreements` (no caller in this repository or any sibling checkout), and
the `"ERROR"` state, which is in neither of EDC's state enums.

EDCL-06 settles the agreement-id vocabulary — see the module docstring in
`ds_edc/webhooks.py` for which id correlates and why.
"""
from __future__ import annotations

import ds_edc
from ds_edc.client import (
    _ACTIVE_TRANSFER_STATES,
    _FINALIZED_STATES,
    _TERMINAL_STATES,
    _TERMINAL_TRANSFER_STATES,
    EdcManagementClient,
)
from ds_edc.webhooks import ContractNegotiationEvent, TransferProcessEvent

#: EDC 0.16.0 `ContractNegotiationStates` / `TransferProcessStates`. A state
#: this client names that is not here can never match.
EDC_NEGOTIATION_STATES = {
    "INITIAL", "REQUESTING", "REQUESTED", "OFFERING", "OFFERED", "ACCEPTING",
    "ACCEPTED", "AGREEING", "AGREED", "VERIFYING", "VERIFIED", "FINALIZING",
    "FINALIZED", "TERMINATING", "TERMINATED",
}
EDC_TRANSFER_STATES = {
    "INITIAL", "PROVISIONING", "PROVISIONING_REQUESTED", "PROVISIONED",
    "REQUESTING", "REQUESTED", "STARTING", "STARTED", "SUSPENDING", "SUSPENDED",
    "COMPLETING", "COMPLETED", "TERMINATING", "TERMINATED",
    "DEPROVISIONING", "DEPROVISIONING_REQUESTED", "DEPROVISIONED",
}


def test_every_negotiation_state_this_client_matches_is_one_edc_produces():
    unknown = (_FINALIZED_STATES | _TERMINAL_STATES) - EDC_NEGOTIATION_STATES
    assert not unknown, f"{unknown} is not an EDC negotiation state"


def test_every_transfer_state_this_client_matches_is_one_edc_produces():
    named = _ACTIVE_TRANSFER_STATES | _TERMINAL_TRANSFER_STATES
    unknown = named - EDC_TRANSFER_STATES
    assert not unknown, f"{unknown} is not an EDC transfer state"


def test_error_is_not_treated_as_a_state():
    """It was in both terminal sets. EDC carries failure as `errorDetail` on a
    `TERMINATED` entity, so the branch was unreachable while reading as the
    handler for exactly the case operators care about."""
    assert "ERROR" not in _TERMINAL_STATES
    assert "ERROR" not in _TERMINAL_TRANSFER_STATES


def test_timeout_is_not_a_state_either():
    """It was synthesised, not matched — the other half of the same confusion.
    `EdcPollTimeout` replaced it; see `test_polling.py`."""
    every = (_FINALIZED_STATES | _TERMINAL_STATES
             | _ACTIVE_TRANSFER_STATES | _TERMINAL_TRANSFER_STATES)
    assert "TIMEOUT" not in every


def test_the_duplicate_and_uncalled_methods_are_gone():
    for name in ("get_contract_negotiation_agreement", "query_agreements"):
        assert not hasattr(EdcManagementClient, name), (
            f"{name} is back; it had no caller here or in any sibling checkout"
        )


def test_get_negotiation_is_the_one_way_to_read_a_negotiation():
    """`get_contract_negotiation_agreement` issued the identical request under a
    name suggesting it returned an agreement."""
    assert hasattr(EdcManagementClient, "get_negotiation")


def test_the_package_exports_what_it_documents():
    for name in ds_edc.__all__:
        assert hasattr(ds_edc, name), f"{name} is in __all__ and not importable"
    assert "EdcPollTimeout" in ds_edc.__all__
    assert "DSP_PATH_SEGMENT" in ds_edc.__all__


# -- EDCL-06 · the two agreement ids ------------------------------------------

FINALIZED = {
    "id": "evt-1",
    "type": "ContractNegotiationFinalized",
    "payload": {
        "contractNegotiationId": "neg-1",
        "contractAgreementId": "local-entity-id",
        "dspAgreementId": "shared-dsp-id",
        "assetId": "energy.meter_readings",
    },
}


def test_the_local_and_shared_agreement_ids_are_both_reachable():
    """The connector reached past the model into `payload["dspAgreementId"]`,
    which is what an unsettled vocabulary looks like from the outside."""
    event = ContractNegotiationEvent(**FINALIZED)
    assert event.agreement_id == "local-entity-id"
    assert event.dsp_agreement_id == "shared-dsp-id"
    assert event.negotiation_id == "neg-1"


def test_they_are_distinct_and_the_test_would_notice_if_they_were_aliased():
    event = ContractNegotiationEvent(**FINALIZED)
    assert event.agreement_id != event.dsp_agreement_id


def test_a_negotiation_with_no_agreement_yet_has_neither():
    event = ContractNegotiationEvent(
        id="evt-0", type="ContractNegotiationRequested",
        payload={"contractNegotiationId": "neg-1"},
    )
    assert event.agreement_id is None
    assert event.dsp_agreement_id is None


def test_a_transfer_names_the_agreement_it_was_started_with():
    event = TransferProcessEvent(
        id="evt-2", type="TransferProcessStarted",
        payload={"transferProcessId": "t-1", "contractId": "local-entity-id",
                 "assetId": "energy.meter_readings"},
    )
    assert event.transfer_id == "t-1"
    assert event.agreement_id == "local-entity-id"
    assert event.asset_id == "energy.meter_readings"


def test_the_envelope_id_is_the_fallback_for_a_missing_entity_id():
    event = TransferProcessEvent(id="evt-3", type="TransferProcessStarted", payload={})
    assert event.transfer_id == "evt-3"
