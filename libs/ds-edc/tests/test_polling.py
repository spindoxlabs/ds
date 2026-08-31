"""EDCL-04 · rulebook data-exchange X-10 — a timeout is reported as a timeout.

Both polls used to build a `NegotiationState` / `TransferState` with
`state="TIMEOUT"` and hand it back. Callers compare that field against real EDC
state names, so "we stopped waiting" was shaped exactly like "the counterparty
refused" — and `EdcPollTimeout` exists so the two can no longer be confused by a
caller that forgets to check.
"""

from __future__ import annotations

import time

import pytest
from conftest import json_response

from ds_edc.client import EdcPollTimeout


def states(*sequence):
    """Answer each poll with the next state, repeating the last one forever."""
    seq = list(sequence)

    def handler(_request):
        state = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(state, dict):
            return json_response(200, state)
        return json_response(200, {"state": state})

    return handler


# -- Negotiation ---------------------------------------------------------------


async def test_finalized_returns_the_agreement(edc_client):
    client, _ = edc_client(
        states(
            "REQUESTING",
            "REQUESTED",
            {"state": "FINALIZED", "contractAgreementId": "ag-1"},
        )
    )
    result = await client.poll_negotiation("n", poll_interval=0, timeout=5)
    assert result.state == "FINALIZED"
    assert result.contract_agreement_id == "ag-1"


async def test_agreed_also_ends_the_poll_and_carries_the_agreement(edc_client):
    """`AGREED` and `VERIFIED` are success states too, not intermediate ones.

    EDC creates the agreement on the `AGREEING` → `AGREED` transition, so the id
    is there by the time this returns — which matters because
    `consumer_service.run_flow` fails the flow on a success state with no
    agreement id.
    """
    client, _ = edc_client(states({"state": "AGREED", "contractAgreementId": "ag-1"}))
    result = await client.poll_negotiation("n", poll_interval=0, timeout=5)
    assert (result.state, result.contract_agreement_id) == ("AGREED", "ag-1")


async def test_terminated_returns_the_reason(edc_client):
    client, _ = edc_client(
        states({"state": "TERMINATED", "errorDetail": "policy evaluation failed"})
    )
    result = await client.poll_negotiation("n", poll_interval=0, timeout=5)
    assert result.state == "TERMINATED"
    assert result.error_detail == "policy evaluation failed"


async def test_a_stalled_negotiation_raises_rather_than_reporting_a_state(edc_client):
    """The counterfactual.

    Old behaviour: `NegotiationState(state="TIMEOUT")`, which
    `consumer_service.run_flow` turned into "Negotiation failed: state=TIMEOUT"
    — a sentence that reads as a protocol outcome and is not one.
    """
    client, _ = edc_client(states("REQUESTED"))
    with pytest.raises(EdcPollTimeout) as exc:
        await client.poll_negotiation("n-42", poll_interval=0, timeout=0)
    assert exc.value.entity_id == "n-42"
    assert exc.value.last_state == "REQUESTED"
    assert "REQUESTED" in str(exc.value)


async def test_the_timeout_is_a_timeout_error(edc_client):
    """So `except TimeoutError` catches it without importing this library."""
    client, _ = edc_client(states("REQUESTED"))
    with pytest.raises(TimeoutError):
        await client.poll_negotiation("n", poll_interval=0, timeout=0)


# -- Transfer ------------------------------------------------------------------


async def test_started_is_the_success_state(edc_client):
    client, _ = edc_client(states("REQUESTED", "STARTED"))
    result = await client.poll_transfer("t", poll_interval=0, timeout=5)
    assert result.state == "STARTED"


async def test_a_stalled_transfer_raises(edc_client):
    client, _ = edc_client(states("PROVISIONING"))
    with pytest.raises(EdcPollTimeout) as exc:
        await client.poll_transfer("t-7", poll_interval=0, timeout=0)
    assert exc.value.last_state == "PROVISIONING"


# -- The deadline actually bounds the wait -------------------------------------


async def test_a_slow_control_plane_does_not_extend_the_timeout(edc_client):
    """The half of this row that only shows up when it matters.

    `elapsed` advanced by `poll_interval` and ignored how long each request
    took, so against an EDC answering slowly — precisely the case a timeout is
    for — a 120s budget ran for as long as the requests did. Here each answer
    costs 40ms against a 100ms budget: by wall clock the third answer is already
    past the deadline, and counting sleeps alone would allow many more.
    """

    async def slow(_request):
        time.sleep(0.04)
        return json_response(200, {"state": "REQUESTED"})

    client, fake = edc_client(slow)
    started = time.monotonic()
    with pytest.raises(EdcPollTimeout):
        await client.poll_negotiation("n", poll_interval=0.0, timeout=0.1)
    waited = time.monotonic() - started

    assert waited < 0.5, f"poll ran {waited:.2f}s against a 0.1s timeout"
    assert len(fake.requests) <= 4, (
        f"{len(fake.requests)} polls in a 0.1s budget at 40ms each — "
        "the loop is counting sleeps, not elapsed time"
    )


async def test_at_least_one_state_is_read_before_giving_up(edc_client):
    """A zero timeout must still ask once.

    Otherwise a caller that passes an aggressive timeout reports a stall having
    never looked, and the `last_state` on the exception is a guess.
    """
    client, fake = edc_client(states("REQUESTED"))
    with pytest.raises(EdcPollTimeout):
        await client.poll_negotiation("n", poll_interval=0, timeout=0)
    assert len(fake.requests) == 1
