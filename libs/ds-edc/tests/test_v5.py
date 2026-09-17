"""The client speaks EDC 0.18.0's v5 management API, behind a bearer token.

What each test pins was measured against a running 0.18.0 runtime (plan
`the-management-api-is-v3-behind-one-key`): the path shape, the array
`@context` the schemas require, the DSP compact policy form, the `Criterion`
type in a filter, the callback payload an EDR arrives in.
"""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import BASE, CONTEXT_ID, ROOT, json_response, status_only

from ds_edc import (
    DEFAULT_API_VERSION,
    MANAGEMENT_CONTEXT,
    TRANSFER_STARTED_EVENT,
    CallbackAddress,
    EdcManagementClient,
    OdrlConversionError,
    TransferProcessStartedEvent,
    to_dsp_compact,
)
from ds_edc.schemas import (
    AssetCreate,
    CatalogRequest,
    ContractDefCreate,
    DataAddress,
    PolicyCreate,
    TransferRequest,
)

V2 = "https://w3id.org/edc/connector/management/v2"


def _body(request: httpx.Request) -> dict:
    return json.loads(request.read())


# -- Paths ---------------------------------------------------------------------


def test_the_version_is_v5beta_on_0_18_0():
    """EDC main serves `/v5`; 0.18.0 serves `/v5beta`. One setting flips it."""
    assert DEFAULT_API_VERSION == "v5beta"


@pytest.mark.parametrize(
    "call,path",
    [
        (lambda c: c.list_assets(), "/assets/request"),
        (lambda c: c.get_asset("a b"), "/assets/a%20b"),
        (lambda c: c.list_policies(), "/policydefinitions/request"),
        (lambda c: c.list_contract_definitions(), "/contractdefinitions/request"),
        (lambda c: c.get_negotiation("n"), "/contractnegotiations/n"),
        (lambda c: c.get_transfer("t"), "/transferprocesses/t"),
        (lambda c: c.list_transfers(), "/transferprocesses/request"),
        (lambda c: c.get_agreement("urn:uuid:1"), "/contractagreements/urn%3Auuid%3A1"),
    ],
)
async def test_every_resource_is_under_the_participant_context(edc_client, call, path):
    client, fake = edc_client(lambda _r: json_response(200, []))
    await call(client)
    assert fake.last.url.raw_path.decode() == ROOT + path


async def test_the_version_segment_is_a_setting():
    captured = []
    client = EdcManagementClient(BASE, CONTEXT_ID, api_version="v5")
    client._http = httpx.AsyncClient(
        base_url=BASE,
        transport=httpx.MockTransport(
            lambda r: captured.append(r) or json_response(200, [])
        ),
    )
    await client.list_assets()
    assert captured[0].url.path.startswith("/management/v5/participants/")


async def test_resume_stays_on_ds_s_own_route(edc_client):
    """Not a v5 resource: ds's extension serves it for the runtime's one context."""
    client, fake = edc_client(lambda _r: json_response(200, {"outcome": "resumed"}))
    await client.resume_negotiation("n")
    assert fake.last.url.path == "/management/dataspaces/negotiations/n/resume"


def test_a_participant_context_is_required():
    with pytest.raises(ValueError):
        EdcManagementClient(BASE, "")


# -- Authentication ------------------------------------------------------------


async def test_every_request_carries_the_bearer_token(edc_client):
    client, fake = edc_client(lambda _r: json_response(200, []))
    await client.list_assets()
    assert fake.last.headers["Authorization"] == "Bearer org-token"
    assert "x-api-key" not in {k.lower() for k in fake.last.headers}


class _RotatingSource:
    def __init__(self) -> None:
        self.issued = 0
        self.invalidated = 0

    async def __call__(self) -> str:
        self.issued += 1
        return f"token-{self.issued}"

    def invalidate(self) -> None:
        self.invalidated += 1


async def test_a_401_refreshes_the_token_once():
    source = _RotatingSource()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return status_only(401) if len(seen) == 1 else json_response(200, [])

    client = EdcManagementClient(BASE, CONTEXT_ID, token_source=source)
    client._http = httpx.AsyncClient(
        base_url=BASE, auth=client._http.auth, transport=httpx.MockTransport(handler)
    )
    assert await client.list_assets() == []
    assert seen == ["Bearer token-1", "Bearer token-2"]
    assert source.invalidated == 1


async def test_a_second_401_reaches_the_caller():
    source = _RotatingSource()
    client = EdcManagementClient(BASE, CONTEXT_ID, token_source=source)
    client._http = httpx.AsyncClient(
        base_url=BASE,
        auth=client._http.auth,
        transport=httpx.MockTransport(lambda _r: status_only(401, "Not authorized")),
    )
    with pytest.raises(httpx.HTTPStatusError, match="401"):
        await client.list_assets()
    assert source.issued == 2


# -- Bodies: what the v5 schemas require ---------------------------------------


def _all_bodies() -> dict[str, dict]:
    return {
        "asset": AssetCreate(id="a", data_address=DataAddress()).to_edc(),
        "policy": PolicyCreate(
            id="p", policy={"@type": "odrl:Set", "odrl:permission": []}
        ).to_edc(),
        "contract": ContractDefCreate(
            id="c", access_policy_id="p", contract_policy_id="p"
        ).to_edc(),
        "catalog": CatalogRequest(
            counter_party_address="http://x", counter_party_id="did:web:x"
        ).to_edc(),
        "transfer": TransferRequest(
            contract_agreement_id="ag",
            counter_party_address="http://x",
            asset_id="a",
            connector_id="did:web:x",
        ).to_edc(),
    }


@pytest.mark.parametrize("name", list(_all_bodies()))
def test_every_body_carries_the_v2_context_as_an_array(name):
    """A JSON-object `@context` is a 400: "object found, array expected"."""
    body = _all_bodies()[name]
    assert body["@context"] == [V2] == MANAGEMENT_CONTEXT
    assert body["@type"]


def test_a_contract_definition_selector_is_typed_criterion():
    body = ContractDefCreate(
        id="c",
        access_policy_id="p",
        contract_policy_id="p",
        assets_selector=[
            {
                "@type": "CriterionDto",
                "operandLeft": "x",
                "operator": "=",
                "operandRight": "a",
            }
        ],
    ).to_edc()
    assert body["assetsSelector"][0]["@type"] == "Criterion"


def test_a_transfer_request_carries_no_v3_only_fields():
    body = _all_bodies()["transfer"]
    assert not {"assetId", "connectorId", "dataDestination"} & set(body)


async def test_a_state_filter_is_a_typed_criterion(edc_client):
    client, fake = edc_client(lambda _r: json_response(200, []))
    await client.query_negotiations(state="FINALIZED")
    criterion = _body(fake.last)["filterExpression"][0]
    assert criterion["@type"] == "Criterion"


async def test_terminate_bodies_are_v5_shaped(edc_client):
    client, fake = edc_client(lambda _r: status_only(204))
    await client.terminate_negotiation("n", "why")
    body = _body(fake.last)
    assert body == {
        "@context": MANAGEMENT_CONTEXT,
        "@type": "TerminateNegotiation",
        "reason": "why",
    }


def test_an_asset_property_under_an_undeclared_prefix_is_written_in_full():
    """v5 takes only IRIs in `@context`, so an asset's own prefixes cannot
    travel with it; the absolute IRI is the same property."""
    body = AssetCreate(
        id="a",
        data_address=DataAddress(),
        properties={
            "ex:thing": "1",
            "dct:conformsTo": "https://example.org/model",
            "name": "n",
            "unknown:x": "2",
        },
        context={"@vocab": "https://w3id.org/edc/v0.0.1/ns/", "ex": "https://ex.org/"},
    ).to_edc()
    props = body["properties"]
    assert props["https://ex.org/thing"] == "1"
    # `dct` is declared by the management context itself.
    assert props["dct:conformsTo"] == "https://example.org/model"
    assert props["name"] == "n"
    # An undeclared prefix is left as EDC stored it under v3.
    assert props["unknown:x"] == "2"


# -- Callbacks -----------------------------------------------------------------


def test_a_callback_names_a_header_and_a_vault_alias():
    cb = CallbackAddress(
        uri="http://connector/webhooks/edc-callback",
        events=[TRANSFER_STARTED_EVENT],
        auth_key="X-Ds-Callback-Key",
        auth_code_id="ds-connector-callback-key",
    )
    assert cb.to_edc() == {
        "@type": "CallbackAddress",
        "transactional": False,
        "uri": "http://connector/webhooks/edc-callback",
        "events": ["transfer.process.started"],
        # Prefixed: the v2 context does not map the bare terms, and EDC drops
        # them silently (measured on 0.18.0).
        "edc:authKey": "X-Ds-Callback-Key",
        "edc:authCodeId": "ds-connector-callback-key",
    }


def test_a_header_without_a_vault_alias_is_refused():
    """EDC refuses such a callback at dispatch time, in its own log."""
    with pytest.raises(ValueError, match="auth_code_id"):
        CallbackAddress(uri="http://x", events=["e"], auth_key="X-K").to_edc()


async def test_a_transfer_carries_its_callback(edc_client):
    client, fake = edc_client(lambda _r: json_response(200, {"@id": "t-1"}))
    cb = CallbackAddress(uri="http://c/cb", events=[TRANSFER_STARTED_EVENT])
    transfer_id = await client.start_transfer(
        TransferRequest(
            contract_agreement_id="ag",
            counter_party_address="http://x",
            asset_id="a",
            connector_id="did:web:x",
            callback_addresses=[cb],
        )
    )
    assert transfer_id == "t-1"
    assert _body(fake.last)["callbackAddresses"] == [cb.to_edc()]


#: `TransferProcessStarted` as EDC 0.18.0 posted it to a callback (measured,
#: token shortened).
STARTED = {
    "id": "7707bef2",
    "at": 1789645894183,
    "payload": {
        "transferProcessId": "t-1",
        "callbackAddresses": [],
        "assetId": "datasets.gold.grid_capacity",
        "type": "CONSUMER",
        "contractId": "ag-1",
        "participantContextId": "did:web:consumer.example.org",
        "protocol": "dataspace-protocol-http:2025-1",
        "dataAddress": {
            "properties": {
                "https://w3id.org/edc/v0.0.1/ns/type": "https://w3id.org/idsa/v4.1/HTTP",
                "https://w3id.org/edc/v0.0.1/ns/endpoint": "http://dp/query",
                "https://w3id.org/edc/v0.0.1/ns/authType": "bearer",
                "https://w3id.org/edc/v0.0.1/ns/authorization": "eyJ.token",
            }
        },
    },
    "type": "TransferProcessStarted",
}


def test_the_started_event_carries_the_edr():
    event = TransferProcessStartedEvent(**STARTED)
    assert event.is_started
    assert event.transfer_id == "t-1"
    assert event.agreement_id == "ag-1"
    assert event.asset_id == "datasets.gold.grid_capacity"
    assert event.participant_context_id == "did:web:consumer.example.org"
    edr = event.edr()
    assert (edr.endpoint, edr.authorization) == ("http://dp/query", "eyJ.token")


def test_an_event_without_a_data_address_has_no_edr():
    event = TransferProcessStartedEvent(
        type="TransferProcessStarted", payload={"transferProcessId": "t"}
    )
    with pytest.raises(ValueError):
        event.edr()


# -- ODRL: the DSP compact form ------------------------------------------------

#: What ds's governance mapper writes (abbreviated from the dev catalogue).
MAPPED = {
    "@context": {
        "odrl": "http://www.w3.org/ns/odrl/2/",
        "dsp-policy": "https://w3id.org/dsp/policy/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    },
    "@type": "odrl:Set",
    "@id": "p",
    "odrl:assigner": {"@id": "did:web:rec.example.org"},
    "odrl:permission": [
        {
            "odrl:action": {"@id": "dsp-policy:Query"},
            "odrl:constraint": [
                {
                    "odrl:leftOperand": "dsp-policy:Membership",
                    "odrl:operator": {"@id": "odrl:eq"},
                    "odrl:rightOperand": {
                        "@value": "owner:example-org:member",
                        "@type": "xsd:string",
                    },
                },
                {
                    "odrl:leftOperand": "http://www.w3.org/ns/odrl/2/purpose",
                    "odrl:operator": {"@id": "odrl:isAnyOf"},
                    "odrl:rightOperand": ["https://w3id.org/dsp/policy/purpose/A"],
                },
            ],
        },
        {"odrl:action": {"@id": "odrl:aggregate"}},
    ],
}


def test_the_mapper_s_policy_becomes_the_profile_s_compact_form():
    """The shape EDC 0.18.0 accepted, and stored byte-identically to v3."""
    assert to_dsp_compact(MAPPED) == {
        "@type": "Set",
        "@id": "p",
        "assigner": "did:web:rec.example.org",
        "permission": [
            {
                "action": "https://w3id.org/dsp/policy/Query",
                "constraint": [
                    {
                        "leftOperand": "https://w3id.org/dsp/policy/Membership",
                        "operator": "eq",
                        "rightOperand": "owner:example-org:member",
                    },
                    {
                        "leftOperand": "http://www.w3.org/ns/odrl/2/purpose",
                        "operator": "isAnyOf",
                        "rightOperand": ["https://w3id.org/dsp/policy/purpose/A"],
                    },
                ],
            },
            {"action": "http://www.w3.org/ns/odrl/2/aggregate"},
        ],
    }


def test_conversion_is_idempotent():
    once = to_dsp_compact(MAPPED)
    assert to_dsp_compact(once) == once


def test_a_bare_action_term_is_written_out():
    """`use` is a profile term, but a bare word the profile does not define
    would resolve against the document base — so every action is absolute."""
    assert to_dsp_compact({"permission": [{"action": "use"}]}) == {
        "permission": [{"action": "http://www.w3.org/ns/odrl/2/use"}]
    }


def test_an_operator_the_profile_does_not_define_is_refused():
    with pytest.raises(OdrlConversionError, match="operator"):
        to_dsp_compact(
            {
                "permission": [
                    {
                        "action": "use",
                        "constraint": [
                            {
                                "leftOperand": "x:y",
                                "operator": "odrl:madeUp",
                                "rightOperand": "1",
                            }
                        ],
                    }
                ]
            }
        )


def test_a_typed_literal_other_than_string_keeps_its_type():
    out = to_dsp_compact(
        {
            "@context": {"xsd": "http://www.w3.org/2001/XMLSchema#"},
            "permission": [
                {
                    "action": "use",
                    "constraint": [
                        {
                            "leftOperand": "odrl:count",
                            "operator": "lteq",
                            "rightOperand": {"@value": "5", "@type": "xsd:integer"},
                        }
                    ],
                }
            ],
        }
    )
    assert out["permission"][0]["constraint"][0]["rightOperand"] == {
        "@value": "5",
        "@type": "http://www.w3.org/2001/XMLSchema#integer",
    }


def test_a_logical_constraint_is_converted_inside():
    out = to_dsp_compact(
        {
            "permission": [
                {
                    "action": "use",
                    "constraint": [
                        {
                            "odrl:or": [
                                {
                                    "leftOperand": "odrl:purpose",
                                    "operator": "odrl:eq",
                                    "rightOperand": "a",
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    )
    inner = out["permission"][0]["constraint"][0]["or"][0]
    assert inner["operator"] == "eq"
    assert inner["leftOperand"] == "http://www.w3.org/ns/odrl/2/purpose"
