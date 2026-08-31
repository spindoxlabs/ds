"""Every outbound DSP request names its counterparty.

`counterPartyId` is not metadata — it is the **audience** of the DCP token the
request is authenticated with. Omitted, EDC falls back to its own participant id,
so the consumer asks its STS for a token addressed to itself and the provider
refuses it:

    Token audience claim (aud -> [did:web:consumer…]) did not contain expected
    audience: did:web:provider…

The negotiation request carried no `counterPartyId` for as long as this
repository has existed, and no suite noticed, because the EDC's demo identity
fallback accepted any self-issued token with `iss == sub` and never looked at the
audience. Found the moment that fallback was switched off.
"""

from __future__ import annotations

import pytest
from ds_edc.schemas import CatalogRequest, NegotiationRequest

from connector.registry.participants import Participant, UnknownParticipantError

PROVIDER = "did:web:rec.dataspaces.localhost"
ADDRESS = "http://172.17.0.1:19194/protocol/2025-1"


def _negotiation(**kwargs) -> dict:
    return NegotiationRequest(
        counter_party_address=ADDRESS,
        offer_id="offer-1",
        asset_id="asset-1",
        assigner=PROVIDER,
        **kwargs,
    ).to_edc()


@pytest.mark.rule("X-1")
def test_negotiation_names_the_counterparty():
    assert _negotiation()["counterPartyId"] == PROVIDER


def test_negotiation_counterparty_can_be_stated_explicitly():
    other = "did:web:someone-else.dataspaces.localhost"
    assert _negotiation(counter_party_id=other)["counterPartyId"] == other


@pytest.mark.rule("X-1")
def test_negotiation_falls_back_to_the_assigner_never_to_nothing():
    """The assigner *is* the counterparty for a contract request.

    Defaulting to it is deliberate: there is no case where a negotiation has no
    counterparty, and a `None` here is silently the local participant.
    """
    body = _negotiation()
    assert body["counterPartyId"]
    assert body["counterPartyId"] != ""


@pytest.mark.rule("X-1")
def test_catalog_request_names_the_counterparty():
    body = CatalogRequest(
        counter_party_address=ADDRESS, counter_party_id=PROVIDER
    ).to_edc()
    assert body["counterPartyId"] == PROVIDER


# ── The counterparty a catalog request names ────────────────────────────────


class _Registry:
    def __init__(self, participant):
        self._participant = participant

    def validate(self, address):
        if self._participant is None:
            raise UnknownParticipantError(address)
        return self._participant


class _Edc:
    def __init__(self):
        self.last = None

    async def request_catalog(self, req):
        self.last = req
        return {"dataset": []}


def _service(registry, *, provider_id):
    from connector.services.consumer_service import ConsumerService

    svc = ConsumerService.__new__(ConsumerService)
    svc._registry = registry
    svc._edc = _Edc()
    svc._provider_id = provider_id
    svc._allow_unknown_participants = True
    return svc


@pytest.mark.asyncio
async def test_catalog_counterparty_comes_from_the_registry():
    """Who is at this address — not who we are.

    On a consumer-side deployment `provider_id` is the **local** DID, so the
    fallback made the connector ask its own STS for a token addressed to itself.
    The provider then refused it, and with the demo identity fallback on, nobody
    ever saw that happen.
    """
    registry = _Registry(Participant(id=PROVIDER, dsp_address=ADDRESS))
    svc = _service(registry, provider_id="did:web:third-party.dataspaces.localhost")
    await svc.request_catalog(ADDRESS)
    assert svc._edc.last.counter_party_id == PROVIDER


@pytest.mark.asyncio
async def test_an_explicit_counterparty_wins():
    registry = _Registry(Participant(id=PROVIDER, dsp_address=ADDRESS))
    svc = _service(registry, provider_id="did:web:third-party.dataspaces.localhost")
    other = "did:web:third-party.dataspaces.localhost"
    await svc.request_catalog(ADDRESS, counter_party_id=other)
    assert svc._edc.last.counter_party_id == other
