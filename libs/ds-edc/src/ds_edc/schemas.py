"""EDC v5 Management API request/response Pydantic models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .odrl import to_dsp_compact

DATASPACE_PROTOCOL = "dataspace-protocol-http:2025-1"

#: The ``@context`` of every v5 request body. The v5 schemas require an
#: **array** containing this IRI; a JSON-object context is a 400.
MANAGEMENT_CONTEXT = ["https://w3id.org/edc/connector/management/v2"]

#: EDC's own vocabulary. Properties in a data address the control plane hands
#: over (an EDR, a callback payload) arrive expanded under it.
EDC_NAMESPACE = "https://w3id.org/edc/v0.0.1/ns/"

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


#: Prefixes the v2 management context declares itself, so a key using one
#: needs no rewriting.
_MANAGEMENT_PREFIXES = {"edc", "dct", "dcat"}


def _expand_key(key: str, context: dict[str, Any] | None) -> str:
    """A property key the management context cannot resolve, written in full.

    ``dsp-policy:owner`` is declared only in the asset's own context, which v5
    no longer accepts inline; the absolute IRI means the same thing. Unprefixed
    keys fall under the properties' ``@vocab`` (EDC's namespace) exactly as
    before.
    """
    if ":" not in key or not context:
        return key
    prefix, _, rest = key.partition(":")
    if rest.startswith("//") or prefix in _MANAGEMENT_PREFIXES:
        return key
    base = context.get(prefix)
    return f"{base}{rest}" if isinstance(base, str) else key


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
    #: The asset's own JSON-LD context, when it carries a property outside the
    #: EDC vocabulary.
    #:
    #: `dct:conformsTo` is the case that forced this: a property whose prefix the
    #: context does not declare is stored as an opaque string key, so a consumer
    #: reading the DSP catalogue gets `"dct:conformsTo"` with nothing saying what
    #: `dct` is — a CURIE that looks standard and expands to nothing. Declaring
    #: the prefix is what makes it a DCAT-AP term rather than a private one that
    #: resembles it.
    #:
    #: Only what an asset actually uses: a context prefix nothing references is a
    #: claim about vocabularies this asset speaks.
    context: dict[str, Any] | None = None

    def to_edc(self) -> dict[str, Any]:
        return {
            # The management context declares `dct` and maps `conformsTo`, and
            # v5 accepts only IRIs in the array. A property the asset's own
            # context declared under another prefix is written out in full.
            "@context": MANAGEMENT_CONTEXT,
            "@type": "Asset",
            "@id": self.id,
            # **Null-valued properties are dropped, not sent.** An undeclared
            # model and one declared as "nothing" are different claims, and only
            # the first is what silence means — the same rule the DCAT emitter
            # follows for `dct:conformsTo`. Sending `null` would also put the key
            # in the catalogue for a consumer to read as present-and-empty.
            "properties": {
                _expand_key(k, self.context): v
                for k, v in self.properties.items()
                if v is not None
            },
            "dataAddress": self.data_address.to_edc(),
        }


# -- Policies -----------------------------------------------------------------


class PolicyCreate(BaseModel):
    id: str
    policy: dict[str, Any]  # ODRL Set

    def to_edc(self) -> dict[str, Any]:
        return {
            "@context": MANAGEMENT_CONTEXT,
            "@type": "PolicyDefinition",
            "@id": self.id,
            # v5 validates the DSP profile's compact form; the conversion keeps
            # the meaning (measured: the stored permissions are byte-identical
            # to the v3-era ones).
            "policy": to_dsp_compact(self.policy),
        }


# -- Contract Definitions -----------------------------------------------------


class ContractDefCreate(BaseModel):
    id: str
    access_policy_id: str
    contract_policy_id: str
    assets_selector: list[dict[str, Any]] = []

    def to_edc(self) -> dict[str, Any]:
        selector = [
            {**criterion, "@type": "Criterion"} for criterion in self.assets_selector
        ] or [
            {
                "@type": "Criterion",
                "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                "operator": "=",
                "operandRight": "*",
            }
        ]
        return {
            "@context": MANAGEMENT_CONTEXT,
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
            "@context": MANAGEMENT_CONTEXT,
            "@type": "CatalogRequest",
            "counterPartyAddress": self.counter_party_address,
            "counterPartyId": self.counter_party_id,
            "protocol": DATASPACE_PROTOCOL,
        }
        if self.query_spec:
            body["querySpec"] = {"@type": "QuerySpec", **self.query_spec}
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
            # The DSP schema requires at least one rule, and an offer is
            # matched against what the provider published, so a hand-built
            # empty one could never have succeeded. Callers pass the catalogue's.
            raise ValueError(
                "NegotiationRequest needs the offer's odrl_policy — take it from "
                "the provider's catalogue"
            )

        policy = to_dsp_compact(dict(self.odrl_policy))
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
        policy["@type"] = "Offer"
        return {
            "@context": MANAGEMENT_CONTEXT,
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


class CallbackAddress(BaseModel):
    """Where EDC posts the events of one negotiation or transfer.

    ``auth_key`` is the **header name** EDC sets, and ``auth_code_id`` the
    **vault alias** of its value — EDC resolves the secret in its own vault
    (``CallbackHttpClient``); the value never travels in the request.
    """

    uri: str
    events: list[str]
    transactional: bool = False
    auth_key: str | None = None
    auth_code_id: str | None = None

    def to_edc(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "@type": "CallbackAddress",
            "transactional": self.transactional,
            "uri": self.uri,
            "events": list(self.events),
        }
        if self.auth_key:
            if not self.auth_code_id:
                # EDC refuses to dispatch such a callback, at event time and in
                # a log nobody reads — refuse it here, where the caller is.
                raise ValueError("CallbackAddress.auth_key needs auth_code_id")
            # **Prefixed, deliberately.** The v2 management context maps `uri`,
            # `transactional` and `events` on `CallbackAddress` and not these
            # two (EDC 0.18.0 and main), so the bare keys expand to nothing and
            # are dropped without a word — EDC then calls back with no header
            # at all (measured). `edc:` is declared by that context, so the
            # prefixed keys expand to the IRIs EDC's transformer reads. The
            # schema permits them.
            body["edc:authKey"] = self.auth_key
            body["edc:authCodeId"] = self.auth_code_id
        return body


#: The event that carries the EDR on the consumer side.
TRANSFER_STARTED_EVENT = "transfer.process.started"


class TransferRequest(BaseModel):
    contract_agreement_id: str
    counter_party_address: str
    asset_id: str
    connector_id: str
    transfer_type: str = "HttpData-PULL"
    callback_addresses: list[CallbackAddress] = []

    def to_edc(self) -> dict[str, Any]:
        # `assetId`, `connectorId` and `dataDestination` were v3 fields the v5
        # schema does not define; the agreement names the asset and the
        # counterparty, and a pull transfer has no destination to state.
        body: dict[str, Any] = {
            "@context": MANAGEMENT_CONTEXT,
            "@type": "TransferRequest",
            "contractId": self.contract_agreement_id,
            "counterPartyAddress": self.counter_party_address,
            "protocol": DATASPACE_PROTOCOL,
            "transferType": self.transfer_type,
        }
        if self.callback_addresses:
            body["callbackAddresses"] = [cb.to_edc() for cb in self.callback_addresses]
        return body


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
        """Parse an EDR data address, in its compact or expanded form.

        ``endpoint`` and ``authorization`` are the whole content of an EDR: one
        says where the data plane is, the other is the bearer that opens it.
        Defaulting them to ``""`` turned a changed or errored EDC payload into a
        structurally valid EDR that the connector handed to a consumer, who then
        failed at the data plane with no way back to the cause. ``authType`` does
        default, because EDC omits it for the bearer case this platform uses.

        A callback payload carries ``{"properties": {…}}`` with every key under
        EDC's namespace (measured on 0.18.0); a management response carries the
        compacted keys. Both are accepted.
        """
        props = (
            data.get("properties") if isinstance(data.get("properties"), dict) else data
        )
        flat = {str(k).removeprefix(EDC_NAMESPACE): v for k, v in (props or {}).items()}
        missing = [k for k in ("endpoint", "authorization") if not flat.get(k)]
        if missing:
            raise ValueError(
                f"EDC EDR data address is missing {', '.join(missing)}; "
                f"got keys {sorted(flat)}"
            )
        return cls(
            endpoint=str(flat["endpoint"]),
            auth_type=str(flat.get("authType") or "bearer"),
            authorization=str(flat["authorization"]),
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
