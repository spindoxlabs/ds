"""The JSON-LD this library puts on the wire.

Each fix here is paired: the shape a correct caller produces, and the
counterfactual — the input that used to be accepted silently and now must not
be. The silent acceptance is the defect; a test that only asserts the happy
path would have passed against the old code too.
"""

from __future__ import annotations

import pytest

from ds_edc.schemas import (
    DATASPACE_PROTOCOL,
    AssetCreate,
    DataAddress,
    EdrResponse,
    NegotiationRequest,
)

DID = "did:web:provider.dataspaces.localhost"
ASSET = "energy.meter_readings"
OFFER = "meter-readings-offer"


# -- EDCL-08 · DataAddress.extra may not overwrite a typed field ---------------


def test_extra_merges_untyped_keys():
    d = DataAddress(
        base_url="http://172.17.0.1:30002", extra={"ds:owner": "example-org"}
    )
    edc = d.to_edc()
    assert edc["baseUrl"] == "http://172.17.0.1:30002"
    assert edc["ds:owner"] == "example-org"


@pytest.mark.parametrize(
    "key", ["baseUrl", "type", "@type", "proxyPath", "proxyQueryParams"]
)
def test_extra_overwriting_a_typed_field_is_refused(key):
    """The counterfactual: this used to win over the typed field, silently.

    `extra` was merged *after* the typed keys, so an asset published with
    `base_url` pointing at the participant's data plane and an `extra` carrying
    `baseUrl` went to EDC with the second value — and both were present in the
    model, with nothing comparing them.
    """
    d = DataAddress(
        base_url="http://172.17.0.1:30002", extra={key: "http://evil.invalid"}
    )
    with pytest.raises(ValueError, match=key):
        d.to_edc()


def test_asset_create_carries_the_data_address_through():
    asset = AssetCreate(
        id=ASSET,
        properties={"ds:owner": "example-org"},
        data_address=DataAddress(base_url="http://172.17.0.1:30002"),
    )
    edc = asset.to_edc()
    assert edc["@id"] == ASSET
    assert edc["dataAddress"]["baseUrl"] == "http://172.17.0.1:30002"


# -- EDCL-01 · the three fields the normal path used to discard ----------------


def test_offer_is_synthesised_when_no_policy_is_supplied():
    req = NegotiationRequest(
        counter_party_address="http://172.17.0.1:19194/protocol/2025-1",
        offer_id=OFFER,
        asset_id=ASSET,
        assigner=DID,
    )
    policy = req.to_edc()["policy"]
    assert policy["@id"] == OFFER
    assert policy["assigner"] == DID
    assert policy["target"] == ASSET


def test_a_published_offer_is_sent_back_unchanged():
    """DSP requires the offer we return to be the offer we were given.

    So a policy that already names all three is passed through byte-for-byte —
    filling them in from the fields would be the *other* way to get this wrong.
    """
    published = {
        "@context": "http://www.w3.org/ns/odrl.jsonld",
        "@type": "Offer",
        "@id": OFFER,
        "assigner": DID,
        "target": ASSET,
        "permission": [{"action": "use", "constraint": []}],
    }
    req = NegotiationRequest(
        counter_party_address="http://x/protocol/2025-1",
        offer_id=OFFER,
        asset_id=ASSET,
        assigner=DID,
        odrl_policy=published,
    )
    assert req.to_edc()["policy"] == published


def test_fields_fill_gaps_in_a_partial_policy():
    """The regression: with a policy supplied, all three used to be dropped."""
    req = NegotiationRequest(
        counter_party_address="http://x/protocol/2025-1",
        offer_id=OFFER,
        asset_id=ASSET,
        assigner=DID,
        odrl_policy={"@type": "Offer", "permission": []},
    )
    policy = req.to_edc()["policy"]
    assert policy["@id"] == OFFER
    assert policy["assigner"] == DID
    assert policy["target"] == ASSET


def test_node_reference_and_bare_form_are_the_same_identifier():
    """`{"@id": x}` and `x` are one value expanded two ways, not a conflict."""
    req = NegotiationRequest(
        counter_party_address="http://x/protocol/2025-1",
        offer_id=OFFER,
        asset_id=ASSET,
        assigner=DID,
        odrl_policy={"@id": OFFER, "assigner": {"@id": DID}, "target": {"@id": ASSET}},
    )
    assert req.to_edc()["policy"]["assigner"] == {"@id": DID}


def test_prefixed_odrl_keys_are_not_duplicated_in_bare_form():
    """A catalogue answer may be prefixed. Injecting `assigner` beside
    `odrl:assigner` would put two assigners in one offer."""
    req = NegotiationRequest(
        counter_party_address="http://x/protocol/2025-1",
        offer_id=OFFER,
        asset_id=ASSET,
        assigner=DID,
        odrl_policy={"@id": OFFER, "odrl:assigner": DID, "odrl:target": ASSET},
    )
    policy = req.to_edc()["policy"]
    assert "assigner" not in policy
    assert "target" not in policy


@pytest.mark.parametrize(
    "field,policy_key,wrong",
    [
        ("offer_id", "@id", "some-other-offer"),
        ("assigner", "assigner", "did:web:someone-else"),
        ("asset_id", "target", "energy.other_table"),
    ],
)
def test_a_field_contradicting_the_policy_is_refused(field, policy_key, wrong):
    """The counterfactual, and the reason this row mattered.

    A caller that got one of the three wrong used to have it discarded, so the
    negotiation went out looking correct and the mistake surfaced — if at all —
    as a provider-side rejection naming neither the field nor the value.
    """
    kwargs = dict(offer_id=OFFER, asset_id=ASSET, assigner=DID)
    kwargs[field] = wrong
    req = NegotiationRequest(
        counter_party_address="http://x/protocol/2025-1",
        odrl_policy={"@id": OFFER, "assigner": DID, "target": ASSET},
        **kwargs,
    )
    with pytest.raises(ValueError, match=field):
        req.to_edc()


def test_counter_party_id_defaults_to_the_assigner():
    """The DCP token audience. Omitted, EDC addresses the token to itself."""
    req = NegotiationRequest(
        counter_party_address="http://x/protocol/2025-1",
        offer_id=OFFER,
        asset_id=ASSET,
        assigner=DID,
    )
    body = req.to_edc()
    assert body["counterPartyId"] == DID
    assert body["protocol"] == DATASPACE_PROTOCOL


# -- EDCL-05 · an EDR is its endpoint and its bearer ---------------------------


def test_edr_is_parsed():
    edr = EdrResponse.from_edc(
        {
            "endpoint": "http://172.17.0.1:30002",
            "authType": "bearer",
            "authorization": "eyJhbGciOi...",
        }
    )
    assert edr.endpoint == "http://172.17.0.1:30002"
    assert edr.authorization == "eyJhbGciOi..."


def test_auth_type_still_defaults():
    """EDC omits `authType` for the bearer case, so this one *is* a default."""
    edr = EdrResponse.from_edc({"endpoint": "http://x", "authorization": "t"})
    assert edr.auth_type == "bearer"


@pytest.mark.parametrize(
    "payload",
    [
        {"authorization": "t"},  # endpoint absent
        {"endpoint": "http://x"},  # authorization absent
        {"endpoint": "", "authorization": "t"},  # present and empty
        {"endpoint": "http://x", "authorization": ""},
        {},  # EDC returned something else entirely
    ],
)
def test_an_incomplete_edr_is_refused(payload):
    """The counterfactual: these all produced a valid-looking `EdrResponse`.

    The connector then handed a consumer an EDR with `endpoint=""`, and the
    failure surfaced at the data plane with nothing pointing back at the EDC
    response that caused it.
    """
    with pytest.raises(ValueError):
        EdrResponse.from_edc(payload)
