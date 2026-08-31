"""EDCL-03 · rulebook data-exchange X-11 — a failed termination reports as failed.

`terminate_negotiation` swallowed 404 and 409; `terminate_transfer` swallowed
404 and 405 under the heading *"termination endpoint unavailable"*. Both then
returned normally, and the connector answered `{"terminated": true}`.

The consequential case is 409 on a `FINALIZED` negotiation and 405 on a running
transfer: a data subject refuses or revokes, nothing stops, and every surface
says it did.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import json_response, status_only


def responder(*, terminate, state=None):
    """Answer the terminate POST one way and the state GET another."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return terminate
        return json_response(200, {"state": state})

    return handler


# -- The success path ----------------------------------------------------------


async def test_a_negotiation_terminates(edc_client):
    client, fake = edc_client(responder(terminate=status_only(204)))
    await client.terminate_negotiation("n", "All data subjects refused consent")
    assert fake.last.url.path.endswith("/contractnegotiations/n/terminate")
    assert b"All data subjects refused consent" in fake.last.read()


async def test_a_transfer_terminates(edc_client):
    client, fake = edc_client(responder(terminate=status_only(204)))
    await client.terminate_transfer("t", "Consent revoked")
    assert fake.last.url.path.endswith("/transferprocesses/t/terminate")


async def test_the_default_transfer_reason_is_sent(edc_client):
    client, fake = edc_client(responder(terminate=status_only(204)))
    await client.terminate_transfer("t")
    assert b"Revoked by consumer" in fake.last.read()


# -- The counterfactuals -------------------------------------------------------


@pytest.mark.parametrize("status", [404, 405, 500, 503])
async def test_a_negotiation_that_did_not_terminate_raises(edc_client, status):
    client, _ = edc_client(responder(terminate=status_only(status, "nope")))
    with pytest.raises(httpx.HTTPStatusError):
        await client.terminate_negotiation("n", "refused")


@pytest.mark.parametrize("status", [404, 405, 500, 503])
async def test_a_transfer_that_did_not_terminate_raises(edc_client, status):
    """405 is the one the old code named in its log line and then ignored.

    Method Not Allowed means this EDC does not serve the route at all — so no
    transfer this connector ever asked to stop was stopping, and the revocation
    UI said otherwise on every one of them.
    """
    client, _ = edc_client(responder(terminate=status_only(status, "nope")))
    with pytest.raises(httpx.HTTPStatusError):
        await client.terminate_transfer("t", "revoked")


async def test_409_on_a_finalized_negotiation_raises(edc_client):
    """The worst case: the agreement is signed and the refusal cannot undo it.

    Reporting success here told a data subject their refusal had taken effect
    while the consumer held a live agreement.
    """
    client, _ = edc_client(
        responder(terminate=status_only(409, "cannot terminate"), state="FINALIZED")
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.terminate_negotiation("n", "refused")


async def test_409_on_a_started_transfer_raises(edc_client):
    client, _ = edc_client(
        responder(terminate=status_only(409, "cannot terminate"), state="STARTED")
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.terminate_transfer("t", "revoked")


# -- Idempotence, established by reading rather than by assuming ---------------


async def test_409_on_an_already_terminated_negotiation_succeeds(edc_client):
    """The TTL sweep retries into this, and must not treat it as a failure.

    The difference from the old code is that the state is *read back*: this is a
    termination observed, not one inferred from a status code that also covers
    `FINALIZED`.
    """
    client, fake = edc_client(
        responder(terminate=status_only(409, "cannot terminate"), state="TERMINATED")
    )
    await client.terminate_negotiation("n", "expired")
    assert fake.requests[-1].method == "GET"


async def test_409_on_an_already_terminated_transfer_succeeds(edc_client):
    client, _ = edc_client(
        responder(terminate=status_only(409, "cannot terminate"), state="TERMINATED")
    )
    await client.terminate_transfer("t", "revoked")


async def test_an_unreadable_state_after_409_stays_a_failure(edc_client):
    """Fail closed: if we cannot confirm it stopped, we did not stop it."""

    def handler(request):
        if request.method == "POST":
            return status_only(409, "cannot terminate")
        return status_only(500, "control plane down")

    client, _ = edc_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await client.terminate_negotiation("n", "expired")


# -- Resume, which is genuinely allowed to be a non-event ---------------------


async def test_resume_reports_a_missing_negotiation_without_raising(edc_client):
    """Unlike terminate: `resume` is documented as idempotent, and a grant
    arriving after the TTL already terminated the negotiation is a race to
    record, not an error to retry into."""
    client, _ = edc_client(lambda _r: status_only(404))
    assert await client.resume_negotiation("n") == {
        "id": "n",
        "resumed": False,
        "outcome": "not_found",
    }


async def test_resume_still_raises_on_a_real_failure(edc_client):
    client, _ = edc_client(lambda _r: status_only(500, "boom"))
    with pytest.raises(httpx.HTTPStatusError):
        await client.resume_negotiation("n")
