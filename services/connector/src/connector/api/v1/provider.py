"""Provider management routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import (
    get_db,
    get_provider_edc,
    get_settings_dep,
    require_provider_read,
    require_provider_write,
)
from ...services.authorization_service import get_authorized_datasets

router = APIRouter(prefix="/provider", tags=["provider"])


class SyncRequest(BaseModel):
    governance_yaml_path: str | None = None


@router.post("/sync")
async def sync(
    req: SyncRequest | None = None,
    settings: Settings = Depends(get_settings_dep),
    edc=Depends(get_provider_edc),
    _claims: dict = Depends(require_provider_write),
):
    from ds.governance.models import load_odrl_profile

    from ...services.governance import ConnectorGovernanceMapper, load_exposed_datasets
    from ...services.prov_bridge import ProvBridge
    from ...clients.provenance import ProvenanceClient
    from ...services.provider_service import sync_governance

    yaml_path = (req.governance_yaml_path if req else None) or settings.governance_yaml_path
    profile = load_odrl_profile(settings.odrl_profile_path)
    mapper = ConnectorGovernanceMapper(settings.participant_id, settings.participant_base_url, profile=profile)
    prov_client = ProvenanceClient(settings.provenance_url)
    prov = ProvBridge(prov_client, settings.participant_id)
    try:
        result = await sync_governance(yaml_path, edc, mapper, prov)
        return result
    finally:
        await prov_client.close()


@router.get("/authorizations")
async def get_authorizations(
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_provider_read),
):
    """Return consented subject IDs per dataset.

    Read-only query endpoint — external consumers (DSO, compliance tools)
    poll it on their own schedule.
    """
    datasets = await get_authorized_datasets(db)
    return {"datasets": datasets}


# TODO: move behind admin auth before enabling — exposes full governance
# policy structure (access levels, classification, consent rules, row-filter
# columns, enforcement details).
#
# @router.get("/governance/matrix")
# async def governance_matrix(
#     settings: Settings = Depends(get_settings_dep),
# ):
#     from ds.governance.models import load_odrl_profile
#
#     from ...services.governance import load_governance_policy_matrix
#
#     profile = load_odrl_profile(settings.odrl_profile_path)
#     return {
#         "source": settings.governance_yaml_path,
#         "participant_id": settings.participant_id,
#         "matrix": load_governance_policy_matrix(
#             settings.governance_yaml_path,
#             settings.participant_id,
#             settings.participant_base_url,
#             profile=profile,
#         ),
#     }


@router.get("/assets")
async def list_assets(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_assets()


@router.get("/assets/{asset_id:path}")
async def get_asset(asset_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    try:
        return await edc.get_asset(asset_id)
    except Exception:
        raise HTTPException(404, f"Asset {asset_id!r} not found")


@router.delete("/assets/{asset_id:path}", status_code=204)
async def delete_asset(asset_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_write)):
    await edc.delete_asset(asset_id)


@router.get("/policies")
async def list_policies(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_policies()


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(policy_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_write)):
    await edc.delete_policy(policy_id)


@router.get("/contracts")
async def list_contracts(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_contract_definitions()


@router.delete("/contracts/{contract_id}", status_code=204)
async def delete_contract(contract_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_write)):
    await edc.delete_contract_definition(contract_id)


@router.get("/transfers")
async def list_transfers(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_transfers()


@router.get("/transfers/{transfer_id}")
async def get_transfer(transfer_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.get_transfer(transfer_id)
