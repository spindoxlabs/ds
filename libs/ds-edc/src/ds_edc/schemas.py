"""EDC Management API v3 request/response Pydantic models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

DATASPACE_PROTOCOL = "dataspace-protocol-http:2025-1"

#: The version half of the pin — ``2025-1``. The rulebook (data-exchange §6)
#: makes this file the single place the version is decided; every DSP address in
#: the repository has to carry it as a path segment, which is what rule X-2
#: means by *"a participant advertising a DSP endpoint without the suffix is not
#: reachable"*. Derived rather than repeated so the two cannot drift, and checked
#: repository-wide by ``tests/test_protocol_pin.py``.
DSP_VERSION = DATASPACE_PROTOCOL.rsplit(":", 1)[-1]

#: The path segment an EDC protocol endpoint must end with.
DSP_PATH_SEGMENT = f"/protocol/{DSP_VERSION}"


def _id_of(value: Any) -> str:
    """The bare identifier behind a JSON-LD node reference.

    ODRL lets the same field arrive as ``"did:web:x"`` or ``{"@id": "did:web:x"}``
    depending on whether the document has been expanded, and comparing the two
    forms directly reports a conflict that is not one.
    """
    if isinstance(value, dict):
        return str(value.get("@id") or value.get("id") or "")
    return str(value or "")


def _policy_field(policy: dict[str, Any], key: str) -> Any:
    """Read ``key`` from an ODRL document in either its bare or prefixed form."""
    if key in policy:
        return policy[key]
    return policy.get(f"odrl:{key}")


# -- Assets ------------------------------------------------------------------

#: Keys ``DataAddress.to_edc`` writes from its own typed fields. ``extra`` may
#: not name any of them.
_DATA_ADDRESS_TYPED_KEYS = frozenset(
    {"@type", "type", "baseUrl", "proxyPath", "proxyQueryParams"}
)


class DataAddress(BaseModel):
    type: str = "HttpData"
    base_url: str = ""
    proxy_path: str = "false"
    proxy_query_params: str = "true"
    extra: dict[str, str] = {}

    def to_edc(self) -> dict[str, Any]:
        # `extra` used to be merged over the typed keys, so an `extra` carrying
        # `baseUrl` silently replaced `base_url` and the asset was published
        # against a different data plane than the caller passed — with both
        # values present in the model and nothing to compare them against. A
        # collision is a caller bug, not a precedence question.
        clash = sorted(_DATA_ADDRESS_TYPED_KEYS & set(self.extra))
        if clash:
            raise ValueError(
                "DataAddress.extra may not override typed field(s): "
                f"{', '.join(clash)}. "
                "Set them through the model's own fields."
            )
        d: dict[str, Any] = {
            "@type": "DataAddress",
            "type": self.type,
            "baseUrl": self.base_url,
            "proxyPath": self.proxy_path,
            "proxyQueryParams": self.proxy_query_params,
        }
        d.update(self.extra)
        return d


class AssetCreate(BaseModel):
    id: str
    properties: dict[str, Any] = {}
    data_address: DataAddress

    def to_edc(self) -> dict[str, Any]:
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "Asset",
            "@id": self.id,
            "properties": self.properties,
            "dataAddress": self.data_address.to_edc(),
        }


# -- Policies -----------------------------------------------------------------

class PolicyCreate(BaseModel):
    id: str
    policy: dict[str, Any]  # ODRL Set

    def to_edc(self) -> dict[str, Any]:
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "PolicyDefinition",
            "@id": self.id,
            "policy": self.policy,
        }


# -- Contract Definitions -----------------------------------------------------

class ContractDefCreate(BaseModel):
    id: str
    access_policy_id: str
    contract_policy_id: str
    assets_selector: list[dict[str, Any]] = []

    def to_edc(self) -> dict[str, Any]:
        selector = self.assets_selector or [{
            "@type": "CriterionDto",
            "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
            "operator": "=",
            "operandRight": "*",
        }]
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "ContractDefinition",
            "@id": self.id,
            "accessPolicyId": self.access_policy_id,
            "contractPolicyId": self.contract_policy_id,
            "assetsSelector": selector,
        }


# -- Catalog ------------------------------------------------------------------

class CatalogRequest(BaseModel):
    counter_party_address: str
    counter_party_id: str
    query_spec: dict[str, Any] | None = None

    def to_edc(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "counterPartyAddress": self.counter_party_address,
            "counterPartyId": self.counter_party_id,
            "protocol": DATASPACE_PROTOCOL,
        }
        if self.query_spec:
            body["querySpec"] = self.query_spec
        return body


# -- Negotiation --------------------------------------------------------------

class NegotiationRequest(BaseModel):
    counter_party_address: str
    offer_id: str
    asset_id: str
    assigner: str
    odrl_policy: dict[str, Any] | None = None
    #: The counterparty's participant id — its DID. Optional only for callers
    #: that predate it; every ds caller supplies the assigner, which is it.
    counter_party_id: str | None = None

    def _offer(self) -> dict[str, Any]:
        """The ODRL offer this request negotiates over.

        ``offer_id``, ``asset_id`` and ``assigner`` used to be read **only** on
        the fallback path — the branch taken when no ``odrl_policy`` is supplied,
        which is not the normal one. Every ds caller passes a policy, so all
        three were accepted and discarded, and a caller that got one of them
        wrong learned nothing.

        They are now reconciled with the policy instead:

        - absent from the policy → filled in from the field, in the bare form;
        - present and equal → left exactly as the provider published it, because
          DSP requires the offer we send back to match the one we were offered;
        - present and **different** → ``ValueError``. The provider would reject
          that offer anyway, with an error naming neither field.
        """
        if self.odrl_policy is None:
            return {
                "@context": ["http://www.w3.org/ns/odrl.jsonld"],
                "@type": "Offer",
                "@id": self.offer_id,
                "assigner": self.assigner,
                "target": self.asset_id,
                "permission": [],
            }

        policy = dict(self.odrl_policy)
        for key, supplied, field in (
            ("@id", self.offer_id, "offer_id"),
            ("assigner", self.assigner, "assigner"),
            ("target", self.asset_id, "asset_id"),
        ):
            present = _id_of(_policy_field(policy, key))
            if not present:
                if supplied:
                    policy[key] = supplied
            elif supplied and present != supplied:
                raise ValueError(
                    f"NegotiationRequest.{field}={supplied!r} contradicts the supplied "
                    f"odrl_policy, whose {key!r} is {present!r}. The offer sent to a "
                    "provider must be the offer it published."
                )
        return policy

    def to_edc(self) -> dict[str, Any]:
        policy = self._offer()
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "ContractRequest",
            "counterPartyAddress": self.counter_party_address,
            # **The audience of the DCP token this negotiation is authenticated
            # with.** Omitted, EDC falls back to its own participant id, so the
            # consumer asked its STS for a token addressed to *itself* and the
            # provider rejected it: "Token audience claim (aud -> [consumer]) did
            # not contain expected audience: [provider]". Nothing noticed, because
            # the demo identity fallback checks `iss == sub` and no audience at
            # all — this is one of the defects that bypass was hiding.
            "counterPartyId": self.counter_party_id or self.assigner,
            "protocol": DATASPACE_PROTOCOL,
            "policy": policy,
        }


class NegotiationState(BaseModel):
    negotiation_id: str
    state: str
    contract_agreement_id: str | None = None
    error_detail: str | None = None


# -- Transfer -----------------------------------------------------------------

class TransferRequest(BaseModel):
    contract_agreement_id: str
    counter_party_address: str
    asset_id: str
    connector_id: str
    transfer_type: str = "HttpData-PULL"

    def to_edc(self) -> dict[str, Any]:
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "TransferRequest",
            "contractId": self.contract_agreement_id,
            "counterPartyAddress": self.counter_party_address,
            "protocol": DATASPACE_PROTOCOL,
            "assetId": self.asset_id,
            "connectorId": self.connector_id,
            "dataDestination": {"type": "HttpProxy"},
            "transferType": self.transfer_type,
        }


class TransferState(BaseModel):
    transfer_id: str
    state: str
    error_detail: str | None = None


# -- EDR ----------------------------------------------------------------------

class EdrResponse(BaseModel):
    endpoint: str
    auth_type: str = "bearer"
    authorization: str

    @classmethod
    def from_edc(cls, data: dict[str, Any]) -> EdrResponse:
        """Parse EDC's EDR data address.

        ``endpoint`` and ``authorization`` are the whole content of an EDR: one
        says where the data plane is, the other is the bearer that opens it.
        Defaulting them to ``""`` turned a changed or errored EDC payload into a
        structurally valid EDR that the connector handed to a consumer, who then
        failed at the data plane with no way back to the cause. ``authType`` does
        default, because EDC omits it for the bearer case this platform uses.
        """
        missing = [k for k in ("endpoint", "authorization") if not data.get(k)]
        if missing:
            raise ValueError(
                f"EDC EDR data address is missing {', '.join(missing)}; "
                f"got keys {sorted(data)}"
            )
        return cls(
            endpoint=str(data["endpoint"]),
            auth_type=str(data.get("authType") or "bearer"),
            authorization=str(data["authorization"]),
        )


# -- Sync ---------------------------------------------------------------------

class SyncResult(BaseModel):
    synced: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []


# -- Flow ---------------------------------------------------------------------

class FlowRequest(BaseModel):
    counter_party_address: str
    asset_id: str
    assigner: str
    query_params: dict[str, str] = {}


class FlowResult(BaseModel):
    negotiation_id: str
    contract_agreement_id: str
    transfer_id: str
    edr: EdrResponse
