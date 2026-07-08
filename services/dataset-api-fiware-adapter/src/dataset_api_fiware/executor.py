from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from celine.dataset.core.config import get_settings
from celine.dataset.core.datasets import load_dataset_entry
from celine.dataset.db.models.dataset_entry import DatasetEntry
from celine.dataset.schemas.dataset_query import DatasetQueryResult
from celine.dataset.security.governance import enforce_dataset_access
from celine.dataset.security.models import AuthenticatedUser
from celine.dataset.api.dataset_query.row_filters import get_row_filter_specs
from celine.dataset.api.dataset_query.row_filters.utils import is_admin_user

from dataset_api_fiware.client import QuantumLeapClient
from dataset_api_fiware.config import FiwareSettings
from dataset_api_fiware.normalizer import normalize_response
from dataset_api_fiware.row_filters import resolve_fiware_row_filters
from dataset_api_fiware.schemas import FiwareQueryModel

logger = logging.getLogger(__name__)

VALID_BACKEND_TYPES = {"quantumleap", "context_broker"}

_fiware_settings: FiwareSettings | None = None


def get_fiware_settings() -> FiwareSettings:
    global _fiware_settings
    if _fiware_settings is not None:
        return _fiware_settings
    _fiware_settings = FiwareSettings()
    return _fiware_settings


def configure_fiware(settings: FiwareSettings) -> None:
    global _fiware_settings
    _fiware_settings = settings


async def execute_fiware_query(
    *,
    catalogue_db: AsyncSession,
    query: FiwareQueryModel,
    user: Optional[AuthenticatedUser],
    fiware_settings: FiwareSettings | None = None,
) -> DatasetQueryResult:
    fw = fiware_settings or get_fiware_settings()

    if not fw.enabled:
        raise HTTPException(404, "FIWARE query engine is not enabled")

    entry = await load_dataset_entry(db=catalogue_db, dataset_id=query.dataset_id)

    if entry.backend_type not in VALID_BACKEND_TYPES:
        raise HTTPException(
            400,
            f"Dataset {query.dataset_id} has backend_type '{entry.backend_type}', "
            f"expected one of {VALID_BACKEND_TYPES}",
        )

    await enforce_dataset_access(entry=entry, user=user)

    config = entry.backend_config or {}
    base_url = config.get("base_url")
    fiware_service = config.get("fiware_service")
    entity_type = config.get("entity_type") or query.entity_type

    if not base_url or not fiware_service:
        raise HTTPException(
            500,
            f"Dataset {query.dataset_id} missing base_url or fiware_service in backend_config",
        )

    # Row filters → entity ID set
    allowed_entity_ids: list[str] | None = None
    specs = get_row_filter_specs(entry)
    if specs and user is not None and not is_admin_user(user):
        filter_result = await resolve_fiware_row_filters(
            specs=specs,
            user=user,
            rec_registry_url=get_settings().rec_registry_url,
        )
        if filter_result.deny:
            return DatasetQueryResult(
                items=[], offset=query.offset, limit=query.limit, count=0, total=0,
            )
        allowed_entity_ids = filter_result.allowed_entity_ids

    # Clamp limit
    effective_limit = min(query.limit, fw.max_limit)
    query_with_limit = query.model_copy(update={"limit": effective_limit, "entity_type": entity_type})

    # Forward user JWT if configured
    user_token = None
    if fw.jwt_forwarding and user and user.token:
        user_token = user.token

    client = QuantumLeapClient(
        base_url=base_url,
        fiware_service=fiware_service,
        fiware_service_path=config.get("fiware_service_path"),
        timeout_ms=fw.default_timeout_ms,
    )

    data, is_single, is_multi, is_list = await client.query(
        query_with_limit,
        entity_ids=allowed_entity_ids,
        user_token=user_token,
    )

    items = normalize_response(
        data,
        is_single_entity=is_single,
        is_multi_entity=is_multi,
        is_entities_list=is_list,
    )

    return DatasetQueryResult(
        items=items,
        offset=query.offset,
        limit=effective_limit,
        count=len(items),
        total=None,
    )
