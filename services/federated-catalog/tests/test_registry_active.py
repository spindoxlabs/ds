"""The index crawls only active participants — rulebook `C-3`, `DSSC-PUB-25`.

A deactivated participant's offerings must stop being discoverable. Nothing in
the loader said so: it passed no `active_only` and ignored the `active` field the
response model has always carried.

Worth knowing why this reads as defence in depth today. The identity-registry
route narrows to active participants for any caller without
`identity-registry.admin`, and this service holds only `identity-registry.read`
— so a live crawl already saw active participants only. That is a property of
*someone else's* guard and one grant change away from disappearing, and the crawl
is the side that knows it must not republish a removed participant.
"""
from __future__ import annotations

import httpx
import respx

from federated_catalog.registry import load_providers_from_registry

REGISTRY = "http://identity-registry:30005"
PARTICIPANTS = f"{REGISTRY}/admin/participants"


def _participant(did: str, *, active: bool = True, roles=("provider",)) -> dict:
    return {
        "did": did,
        "dsp_address": f"http://edc-{did[-1]}:19194/protocol",
        "roles": list(roles),
        "active": active,
    }


@respx.mock
def test_a_deactivated_participant_is_not_crawled():
    respx.get(PARTICIPANTS).mock(
        return_value=httpx.Response(
            200,
            json=[
                _participant("did:web:a"),
                _participant("did:web:b", active=False),
            ],
        )
    )
    providers = load_providers_from_registry(REGISTRY)
    assert [p.id for p in providers] == ["did:web:a"]


@respx.mock
def test_the_request_asks_the_registry_to_filter_too():
    route = respx.get(PARTICIPANTS).mock(
        return_value=httpx.Response(200, json=[_participant("did:web:a")])
    )
    load_providers_from_registry(REGISTRY)
    assert route.calls.last.request.url.params["active_only"] == "true"


@respx.mock
def test_a_payload_that_does_not_say_is_treated_as_not_active():
    """Absent is not "probably fine".

    `active` is part of the response model, so a payload without it is one this
    loader does not understand — and guessing "still admitted" republishes the
    offerings of a participant that may have been removed. The safe reading of an
    unknown shape is the one that publishes less.
    """
    stale = _participant("did:web:legacy")
    del stale["active"]
    respx.get(PARTICIPANTS).mock(return_value=httpx.Response(200, json=[stale]))
    assert load_providers_from_registry(REGISTRY) == []


@respx.mock
def test_a_consumer_only_participant_is_still_skipped():
    respx.get(PARTICIPANTS).mock(
        return_value=httpx.Response(
            200,
            json=[
                _participant("did:web:c", roles=("consumer",)),
                _participant("did:web:d", roles=("consumer", "provider")),
            ],
        )
    )
    providers = load_providers_from_registry(REGISTRY)
    assert [p.id for p in providers] == ["did:web:d"]
