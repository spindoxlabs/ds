"""Async httpx client for EDC Management API v3."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

import httpx

from .schemas import (
    AssetCreate,
    CatalogRequest,
    ContractDefCreate,
    EdrResponse,
    NegotiationRequest,
    NegotiationState,
    PolicyCreate,
    TransferRequest,
    TransferState,
)

log = logging.getLogger(__name__)

_FINALIZED_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
_TERMINAL_STATES = {"TERMINATED", "ERROR"}
_ACTIVE_TRANSFER_STATES = {"STARTED"}
_TERMINAL_TRANSFER_STATES = {"COMPLETED", "TERMINATED", "ERROR", "DEPROVISIONING_REQUESTED"}

EDC_CONTEXT = {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}


def _path_id(value: str) -> str:
    return quote(value, safe="")


class EdcManagementClient:
    """Typed async wrapper around the EDC Management API v3."""

    def __init__(self, base_url: str, api_key: str | None = None):
        headers: dict[str, str] = {}
        if api_key:
            headers["X-Api-Key"] = api_key
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _raise_with_body(r: httpx.Response, operation: str) -> None:
        if r.is_success:
            return
        body = r.text[:500]
        log.error("EDC %s failed (%s): %s", operation, r.status_code, body)
        raise httpx.HTTPStatusError(
            f"EDC {operation} {r.status_code}: {body}",
            request=r.request,
            response=r,
        )

    # -- Assets ---------------------------------------------------------------

    async def create_asset(self, asset: AssetCreate) -> dict[str, Any]:
        r = await self._http.post("/v3/assets", json=asset.to_edc())
        self._raise_with_body(r, "create_asset")
        return r.json()

    async def get_asset(self, asset_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/assets/{_path_id(asset_id)}")
        r.raise_for_status()
        return r.json()

    async def list_assets(self) -> list[dict[str, Any]]:
        r = await self._http.post(
            "/v3/assets/request",
            json={"@context": EDC_CONTEXT, "@type": "QuerySpec"},
        )
        r.raise_for_status()
        return r.json()

    async def delete_asset(self, asset_id: str) -> None:
        r = await self._http.delete(f"/v3/assets/{_path_id(asset_id)}")
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    # -- Policies -------------------------------------------------------------

    async def create_policy(self, policy: PolicyCreate) -> dict[str, Any]:
        r = await self._http.post("/v3/policydefinitions", json=policy.to_edc())
        self._raise_with_body(r, "create_policy")
        return r.json()

    async def list_policies(self) -> list[dict[str, Any]]:
        r = await self._http.post("/v3/policydefinitions/request", json={})
        r.raise_for_status()
        return r.json()

    async def delete_policy(self, policy_id: str) -> None:
        r = await self._http.delete(f"/v3/policydefinitions/{_path_id(policy_id)}")
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    # -- Contract Definitions -------------------------------------------------

    async def create_contract_definition(self, cd: ContractDefCreate) -> dict[str, Any]:
        r = await self._http.post("/v3/contractdefinitions", json=cd.to_edc())
        self._raise_with_body(r, "create_contract_definition")
        return r.json()

    async def list_contract_definitions(self) -> list[dict[str, Any]]:
        r = await self._http.post("/v3/contractdefinitions/request", json={})
        r.raise_for_status()
        return r.json()

    async def delete_contract_definition(self, cid: str) -> None:
        r = await self._http.delete(f"/v3/contractdefinitions/{_path_id(cid)}")
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    # -- Catalog --------------------------------------------------------------

    async def request_catalog(self, req: CatalogRequest) -> dict[str, Any]:
        r = await self._http.post("/v3/catalog/request", json=req.to_edc())
        r.raise_for_status()
        return r.json()

    # -- Negotiation ----------------------------------------------------------

    async def start_negotiation(self, req: NegotiationRequest) -> str:
        r = await self._http.post("/v3/contractnegotiations", json=req.to_edc())
        r.raise_for_status()
        return r.json()["@id"]

    async def get_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/contractnegotiations/{_path_id(negotiation_id)}")
        r.raise_for_status()
        return r.json()

    async def poll_negotiation(
        self,
        negotiation_id: str,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> NegotiationState:
        elapsed = 0.0
        while elapsed < timeout:
            data = await self.get_negotiation(negotiation_id)
            state = data.get("state", "")
            agreement_id = data.get("contractAgreementId")
            if state in _FINALIZED_STATES:
                return NegotiationState(
                    negotiation_id=negotiation_id,
                    state=state,
                    contract_agreement_id=agreement_id,
                )
            if state in _TERMINAL_STATES:
                return NegotiationState(
                    negotiation_id=negotiation_id,
                    state=state,
                    error_detail=data.get("errorDetail"),
                )
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return NegotiationState(
            negotiation_id=negotiation_id,
            state="TIMEOUT",
            error_detail=f"Negotiation did not complete within {timeout}s",
        )

    # -- Transfer -------------------------------------------------------------

    async def start_transfer(self, req: TransferRequest) -> str:
        r = await self._http.post("/v3/transferprocesses", json=req.to_edc())
        r.raise_for_status()
        return r.json()["@id"]

    async def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/transferprocesses/{_path_id(transfer_id)}")
        r.raise_for_status()
        return r.json()

    async def terminate_transfer(self, transfer_id: str, reason: str | None = None) -> None:
        r = await self._http.post(
            f"/v3/transferprocesses/{_path_id(transfer_id)}/terminate",
            json={
                "@context": EDC_CONTEXT,
                "@type": "TerminateTransfer",
                "reason": reason or "Revoked by consumer",
            },
        )
        if r.status_code in (404, 405):
            log.warning("Transfer termination endpoint unavailable for %s: %s", transfer_id, r.text)
            return
        r.raise_for_status()

    async def poll_transfer(
        self,
        transfer_id: str,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> TransferState:
        elapsed = 0.0
        while elapsed < timeout:
            data = await self.get_transfer(transfer_id)
            state = data.get("state", "")
            if state in _ACTIVE_TRANSFER_STATES:
                return TransferState(transfer_id=transfer_id, state=state)
            if state in _TERMINAL_TRANSFER_STATES:
                return TransferState(
                    transfer_id=transfer_id,
                    state=state,
                    error_detail=data.get("errorDetail"),
                )
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return TransferState(
            transfer_id=transfer_id,
            state="TIMEOUT",
            error_detail=f"Transfer did not reach STARTED within {timeout}s",
        )

    async def list_transfers(self) -> list[dict[str, Any]]:
        r = await self._http.post(
            "/v3/transferprocesses/request",
            json={"@context": EDC_CONTEXT, "@type": "QuerySpec"},
        )
        r.raise_for_status()
        return r.json()

    # -- EDR ------------------------------------------------------------------

    async def get_edr(self, transfer_id: str) -> EdrResponse:
        r = await self._http.get(f"/v3/edrs/{_path_id(transfer_id)}/dataaddress")
        r.raise_for_status()
        return EdrResponse.from_edc(r.json())

    # -- Contract Agreements --------------------------------------------------

    async def get_contract_negotiation_agreement(self, negotiation_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/contractnegotiations/{_path_id(negotiation_id)}")
        r.raise_for_status()
        return r.json()

    # -- Query helpers (used by history API) ----------------------------------

    async def query_negotiations(
        self, offset: int = 0, limit: int = 50, state: str | None = None,
    ) -> list[dict[str, Any]]:
        query_spec: dict[str, Any] = {
            "@context": EDC_CONTEXT,
            "@type": "QuerySpec",
            "offset": offset,
            "limit": limit,
            "sortOrder": "DESC",
            "sortField": "createdAt",
        }
        if state:
            query_spec["filterExpression"] = [{
                "operandLeft": "state",
                "operator": "=",
                "operandRight": state,
            }]
        r = await self._http.post("/v3/contractnegotiations/request", json=query_spec)
        r.raise_for_status()
        return r.json()

    async def query_transfers(
        self, offset: int = 0, limit: int = 50, state: str | None = None,
    ) -> list[dict[str, Any]]:
        query_spec: dict[str, Any] = {
            "@context": EDC_CONTEXT,
            "@type": "QuerySpec",
            "offset": offset,
            "limit": limit,
            "sortOrder": "DESC",
            "sortField": "createdAt",
        }
        if state:
            query_spec["filterExpression"] = [{
                "operandLeft": "state",
                "operator": "=",
                "operandRight": state,
            }]
        r = await self._http.post("/v3/transferprocesses/request", json=query_spec)
        r.raise_for_status()
        return r.json()

    async def get_agreement(self, agreement_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/contractagreements/{_path_id(agreement_id)}")
        r.raise_for_status()
        return r.json()

    async def query_agreements(
        self, offset: int = 0, limit: int = 50,
    ) -> list[dict[str, Any]]:
        query_spec: dict[str, Any] = {
            "@context": EDC_CONTEXT,
            "@type": "QuerySpec",
            "offset": offset,
            "limit": limit,
            "sortOrder": "DESC",
            "sortField": "createdAt",
        }
        r = await self._http.post("/v3/contractagreements/request", json=query_spec)
        r.raise_for_status()
        return r.json()
