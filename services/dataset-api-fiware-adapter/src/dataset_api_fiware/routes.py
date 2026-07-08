from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dataset.db.engine import get_session
from celine.dataset.schemas.dataset_query import DatasetQueryResult
from celine.dataset.security.auth import get_optional_user
from celine.dataset.security.models import AuthenticatedUser
from celine.dataset.core.datasets import load_dataset_entry

from dataset_api_fiware.client import QuantumLeapClient
from dataset_api_fiware.executor import execute_fiware_query
from dataset_api_fiware.normalizer import normalize_entities_list
from dataset_api_fiware.schemas import FiwareQueryModel

router = APIRouter(prefix="/query/fiware", tags=["fiware"])


@router.post(
    "",
    response_model=DatasetQueryResult,
    description="Query a FIWARE/QuantumLeap dataset",
    name="FIWARE query",
)
async def fiware_query(
    body: FiwareQueryModel,
    catalogue_db: AsyncSession = Depends(get_session),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    return await execute_fiware_query(
        catalogue_db=catalogue_db,
        query=body,
        user=user,
    )


@router.get(
    "/entities",
    response_model=DatasetQueryResult,
    description="List entities for a FIWARE dataset",
    name="FIWARE entities",
)
async def fiware_entities(
    dataset_id: str = Query(..., description="Dataset ID"),
    limit: int = Query(default=100, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    catalogue_db: AsyncSession = Depends(get_session),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    from celine.dataset.security.governance import enforce_dataset_access

    entry = await load_dataset_entry(db=catalogue_db, dataset_id=dataset_id)
    await enforce_dataset_access(entry=entry, user=user)

    config = entry.backend_config or {}
    base_url = config.get("base_url")
    fiware_service = config.get("fiware_service")
    entity_type = config.get("entity_type", "")

    if not base_url or not fiware_service:
        from fastapi import HTTPException

        raise HTTPException(500, "Missing base_url or fiware_service in backend_config")

    client = QuantumLeapClient(
        base_url=base_url,
        fiware_service=fiware_service,
        fiware_service_path=config.get("fiware_service_path"),
    )

    raw = await client.list_entities(
        entity_type,
        user_token=user.token if user and user.token else None,
        limit=limit,
        offset=offset,
    )

    items = normalize_entities_list(raw)

    return DatasetQueryResult(
        items=items,
        offset=offset,
        limit=limit,
        count=len(items),
        total=None,
    )
