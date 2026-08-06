"""EDCL-07 · a failure reaches the caller, and it says what EDC said.

`_raise_with_body` was on 6 of 30 methods. The other 24 raised through
`httpx.raise_for_status()`, whose message is the status line only — so an EDC
that explains a 400 in its body was reduced to `Client error '400 Bad Request'`
and the explanation was thrown away at the one place it was in hand.
"""
from __future__ import annotations

import inspect

import httpx
import pytest
from conftest import json_response, status_only

from ds_edc.client import EdcManagementClient
from ds_edc.schemas import (
    AssetCreate,
    CatalogRequest,
    ContractDefCreate,
    DataAddress,
    NegotiationRequest,
    PolicyCreate,
    TransferRequest,
)

REFUSAL = "Asset with ID 'energy.meter_readings' already exists"


def _calls(client: EdcManagementClient):
    """Every method that issues a request, with arguments that reach the wire."""
    asset = AssetCreate(id="a", data_address=DataAddress())
    return {
        "create_asset": lambda: client.create_asset(asset),
        "get_asset": lambda: client.get_asset("a"),
        "list_assets": client.list_assets,
        "delete_asset": lambda: client.delete_asset("a"),
        "create_policy": lambda: client.create_policy(PolicyCreate(id="p", policy={})),
        "list_policies": client.list_policies,
        "delete_policy": lambda: client.delete_policy("p"),
        "create_contract_definition": lambda: client.create_contract_definition(
            ContractDefCreate(id="c", access_policy_id="p", contract_policy_id="p")
        ),
        "list_contract_definitions": client.list_contract_definitions,
        "delete_contract_definition": lambda: client.delete_contract_definition("c"),
        "request_catalog": lambda: client.request_catalog(
            CatalogRequest(counter_party_address="http://x",
                           counter_party_id="did:web:x")
        ),
        "start_negotiation": lambda: client.start_negotiation(
            NegotiationRequest(counter_party_address="http://x", offer_id="o",
                               asset_id="a", assigner="did:web:x")
        ),
        "get_negotiation": lambda: client.get_negotiation("n"),
        "terminate_negotiation": lambda: client.terminate_negotiation("n", "why"),
        "resume_negotiation": lambda: client.resume_negotiation("n"),
        "start_transfer": lambda: client.start_transfer(
            TransferRequest(contract_agreement_id="ag", counter_party_address="http://x",
                            asset_id="a", connector_id="did:web:x")
        ),
        "get_transfer": lambda: client.get_transfer("t"),
        "terminate_transfer": lambda: client.terminate_transfer("t", "why"),
        "list_transfers": client.list_transfers,
        "get_edr": lambda: client.get_edr("t"),
        "query_negotiations": client.query_negotiations,
        "query_transfers": client.query_transfers,
        "get_agreement": lambda: client.get_agreement("ag"),
    }


#: Public methods that issue no request of their own. The polls loop over
#: `get_negotiation` / `get_transfer`, so they inherit the error handling under
#: test here and are checked in `test_polling.py` instead; `close` shuts the
#: transport down.
NOT_A_REQUEST = {"close", "poll_negotiation", "poll_transfer"}


def test_every_request_issuing_method_is_covered_by_this_file():
    """The list above must not fall behind the client.

    A method added without a row here is `EDCL-07` starting over: it would be
    exempt from the error-body check by omission, and nothing would say so.
    """
    public = {
        name for name, fn in inspect.getmembers(EdcManagementClient, inspect.isfunction)
        if not name.startswith("_")
    } - NOT_A_REQUEST
    client = EdcManagementClient("http://x")
    assert public == set(_calls(client))


@pytest.mark.parametrize("name", list(_calls(EdcManagementClient("http://x"))))
async def test_a_refusal_reaches_the_caller_with_edc_s_own_words(edc_client, name):
    client, _ = edc_client(lambda _r: status_only(400, REFUSAL))
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await _calls(client)[name]()
    assert REFUSAL in str(exc.value), f"{name} discarded EDC's response body"
    assert "400" in str(exc.value)


@pytest.mark.parametrize(
    "name", ["delete_asset", "delete_policy", "delete_contract_definition"]
)
async def test_delete_tolerates_404_because_absence_is_the_goal(edc_client, name):
    """Deliberately *not* the same rule as terminate.

    "Delete X" when X is not there has reached the requested end state. "Stop
    transfer X" when X is not there has not stopped anything — which is why
    `test_termination.py` asserts the opposite for those.
    """
    client, _ = edc_client(lambda _r: status_only(404, "not found"))
    await _calls(client)[name]()


@pytest.mark.parametrize(
    "name", ["delete_asset", "delete_policy", "delete_contract_definition"]
)
async def test_delete_still_raises_on_a_real_failure(edc_client, name):
    client, _ = edc_client(lambda _r: status_only(500, "boom"))
    with pytest.raises(httpx.HTTPStatusError):
        await _calls(client)[name]()


# -- The unchecked `r.json()["@id"]` -------------------------------------------

async def test_start_negotiation_returns_the_id(edc_client):
    client, _ = edc_client(lambda _r: json_response(200, {"@id": "neg-1"}))
    assert await client.start_negotiation(
        NegotiationRequest(counter_party_address="http://x", offer_id="o",
                           asset_id="a", assigner="did:web:x")
    ) == "neg-1"


@pytest.mark.parametrize("body,kind", [
    ({"id": "neg-1"}, "json"),          # `id`, not `@id` — a JSON-LD compaction change
    ({}, "json"),
    ([{"@id": "neg-1"}], "json"),       # a list, not an object
    (None, "text"),                     # 200 with a non-JSON body
])
async def test_a_2xx_without_an_id_names_the_operation(edc_client, body, kind):
    """The counterfactual: `r.json()["@id"]` raised `KeyError: '@id'`.

    A stack trace naming a dict subscript, from a 200 response, for a call whose
    name appears nowhere in it.
    """
    resp = json_response(200, body) if kind == "json" else status_only(200, "<html>")
    client, _ = edc_client(lambda _r: resp)
    with pytest.raises(ValueError, match="start_negotiation"):
        await client.start_negotiation(
            NegotiationRequest(counter_party_address="http://x", offer_id="o",
                               asset_id="a", assigner="did:web:x")
        )


# -- The QuerySpec the list calls send -----------------------------------------

@pytest.mark.parametrize("name", [
    "list_assets", "list_policies", "list_contract_definitions", "list_transfers",
])
async def test_list_calls_send_a_json_ld_query_spec(edc_client, name):
    """`list_policies` and `list_contract_definitions` used to send `{}`.

    With no `@context`, EDC expands the body against no vocabulary, so the
    QuerySpec defaults applied by accident. The other two list calls on this
    client always sent the JSON-LD form; these two now agree with them.
    """
    client, fake = edc_client(lambda _r: json_response(200, []))
    await _calls(client)[name]()
    body = fake.last.read().decode()
    assert '"@context"' in body, f"{name} sent a body with no @context"
    assert '"QuerySpec"' in body


async def test_api_key_becomes_the_edc_management_header():
    """EDC's own Management API key, and only here — see the unit's AGENTS.md."""
    client = EdcManagementClient("http://edc.test", api_key="edc-key")
    assert client._http.headers["X-Api-Key"] == "edc-key"
    await client.close()


async def test_no_api_key_sends_no_header():
    client = EdcManagementClient("http://edc.test")
    assert "X-Api-Key" not in client._http.headers
    await client.close()
