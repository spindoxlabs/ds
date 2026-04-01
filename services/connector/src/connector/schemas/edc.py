"""EDC Management API request/response Pydantic models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Assets ─────────────────────────────────────────────────────────────────

class DataAddress(BaseModel):
    type: str = "HttpData"
    base_url: str = ""
    proxy_path: str = "false"
    proxy_query_params: str = "true"
    extra: dict[str, str] = {}

    def to_edc(self) -> dict[str, Any]:
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


# ── Policies ───────────────────────────────────────────────────────────────

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


# ── Contract Definitions ───────────────────────────────────────────────────

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


# ── Catalog ─────────────────────────────────────────────────────────────────

class CatalogRequest(BaseModel):
    counter_party_address: str
    query_spec: dict[str, Any] | None = None

    def to_edc(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "counterPartyAddress": self.counter_party_address,
            "protocol": "dataspace-protocol-http",
        }
        if self.query_spec:
            body["querySpec"] = self.query_spec
        return body


# ── Negotiation ─────────────────────────────────────────────────────────────

class NegotiationRequest(BaseModel):
    counter_party_address: str
    offer_id: str
    asset_id: str
    assigner: str
    odrl_policy: dict[str, Any] | None = None

    def to_edc(self) -> dict[str, Any]:
        policy = self.odrl_policy or {
            "@context": "http://www.w3.org/ns/odrl.jsonld",
            "@type": "odrl:Offer",
            "@id": self.offer_id,
            "odrl:assigner": {"@id": self.assigner},
            "odrl:target": {"@id": self.asset_id},
            "odrl:permission": [],
        }
        return {
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": "ContractRequest",
            "counterPartyAddress": self.counter_party_address,
            "protocol": "dataspace-protocol-http",
            "policy": policy,
        }


class NegotiationState(BaseModel):
    negotiation_id: str
    state: str
    contract_agreement_id: str | None = None
    error_detail: str | None = None


# ── Transfer ─────────────────────────────────────────────────────────────────

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
            "protocol": "dataspace-protocol-http",
            "assetId": self.asset_id,
            "connectorId": self.connector_id,
            "dataDestination": {"type": "HttpProxy"},
            "transferType": self.transfer_type,
        }


class TransferState(BaseModel):
    transfer_id: str
    state: str
    error_detail: str | None = None


# ── EDR ───────────────────────────────────────────────────────────────────────

class EdrResponse(BaseModel):
    endpoint: str
    auth_type: str = "bearer"
    authorization: str

    @classmethod
    def from_edc(cls, data: dict[str, Any]) -> EdrResponse:
        return cls(
            endpoint=data.get("endpoint", ""),
            auth_type=data.get("authType", "bearer"),
            authorization=data.get("authorization", ""),
        )


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncResult(BaseModel):
    synced: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []


# ── Flow ──────────────────────────────────────────────────────────────────────

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
