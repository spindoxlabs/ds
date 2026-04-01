"""Consumer routes: catalog, negotiate, transfer, EDR, flow."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import Settings
from ...dependencies import get_consumer_service, get_settings_dep
from ...schemas.edc import FlowRequest, FlowResult

router = APIRouter(prefix="/consumer", tags=["consumer"])


class CatalogRequest(BaseModel):
    counter_party_address: str
    filters: dict | None = None


class NegotiateRequest(BaseModel):
    counter_party_address: str
    offer_id: str
    asset_id: str
    assigner: str
    odrl_policy: dict | None = None


class TransferStartRequest(BaseModel):
    contract_agreement_id: str
    counter_party_address: str
    asset_id: str
    connector_id: str


@router.post("/catalog")
async def request_catalog(
    req: CatalogRequest,
    svc=Depends(get_consumer_service),
):
    return await svc.request_catalog(req.counter_party_address)


@router.post("/negotiate")
async def start_negotiation(
    req: NegotiateRequest,
    svc=Depends(get_consumer_service),
):
    negotiation_id = await svc.negotiate(
        counter_party_address=req.counter_party_address,
        offer_id=req.offer_id,
        asset_id=req.asset_id,
        assigner=req.assigner,
        odrl_policy=req.odrl_policy,
    )
    return {"negotiation_id": negotiation_id}


@router.get("/negotiations/{negotiation_id}")
async def get_negotiation(
    negotiation_id: str,
    svc=Depends(get_consumer_service),
):
    return await svc._edc.get_negotiation(negotiation_id)


@router.post("/transfer")
async def start_transfer(
    req: TransferStartRequest,
    svc=Depends(get_consumer_service),
):
    transfer_id = await svc.transfer(
        contract_agreement_id=req.contract_agreement_id,
        counter_party_address=req.counter_party_address,
        asset_id=req.asset_id,
        connector_id=req.connector_id,
    )
    return {"transfer_id": transfer_id}


@router.get("/transfers/{transfer_id}")
async def get_transfer(
    transfer_id: str,
    svc=Depends(get_consumer_service),
):
    return await svc._edc.get_transfer(transfer_id)


@router.get("/edr/{transfer_id}")
async def get_edr(
    transfer_id: str,
    svc=Depends(get_consumer_service),
):
    return await svc.get_edr(transfer_id)


@router.post("/flow", response_model=FlowResult)
async def run_flow(
    req: FlowRequest,
    svc=Depends(get_consumer_service),
):
    try:
        return await svc.run_flow(req)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
