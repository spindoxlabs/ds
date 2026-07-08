from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from celine.dataset.security.models import AuthenticatedUser

logger = logging.getLogger(__name__)


class FiwareRowFilterResult:
    """Result of resolving row filters for a FIWARE query."""

    def __init__(
        self,
        *,
        allowed_entity_ids: list[str] | None = None,
        deny: bool = False,
    ):
        self.allowed_entity_ids = allowed_entity_ids
        self.deny = deny


async def resolve_entity_ids_from_rec_registry(
    *,
    user: AuthenticatedUser,
    args: dict[str, Any],
    rec_registry_url: str,
) -> list[str]:
    """Resolve device IDs from REC Registry and map to FIWARE URNs."""
    urn_template = args.get("urn_template")
    if not urn_template:
        logger.warning("rec_registry row filter missing urn_template arg")
        return []

    url = f"{rec_registry_url}/api/v1/members/{user.sub}/devices"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {user.token}"} if user.token else {},
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            devices = resp.json()
    except httpx.HTTPError as exc:
        logger.error("REC Registry request failed: %s", exc)
        raise

    entity_ids = []
    for device in devices:
        device_id = device.get("device_id") or device.get("id", "")
        if device_id:
            entity_ids.append(urn_template.replace("{device_id}", device_id))

    return entity_ids


async def resolve_entity_ids_from_http(
    *,
    user: AuthenticatedUser,
    args: dict[str, Any],
) -> list[str]:
    """Resolve entity IDs from an external HTTP endpoint."""
    url = args.get("url")
    if not url:
        return []

    id_field = args.get("id_field", "id")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {user.token}"} if user.token else {},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.error("HTTP entity ID resolution failed: %s", exc)
        raise

    if isinstance(data, list):
        return [str(item.get(id_field, item) if isinstance(item, dict) else item) for item in data]
    return []


async def resolve_fiware_row_filters(
    *,
    specs: list[dict[str, Any]],
    user: Optional[AuthenticatedUser],
    rec_registry_url: str,
) -> FiwareRowFilterResult:
    """Resolve governance row filter specs into FIWARE entity ID constraints."""
    if not specs or user is None:
        return FiwareRowFilterResult()

    all_entity_ids: list[str] | None = None

    for spec in specs:
        handler = spec.get("handler", "")
        args = spec.get("args") or {}

        if handler == "deny":
            return FiwareRowFilterResult(deny=True)

        if handler == "rec_registry":
            ids = await resolve_entity_ids_from_rec_registry(
                user=user,
                args=args,
                rec_registry_url=rec_registry_url,
            )
            if all_entity_ids is None:
                all_entity_ids = ids
            else:
                # Intersect: entity must be allowed by ALL filters
                id_set = set(ids)
                all_entity_ids = [eid for eid in all_entity_ids if eid in id_set]

        elif handler == "http_in_list":
            ids = await resolve_entity_ids_from_http(user=user, args=args)
            if all_entity_ids is None:
                all_entity_ids = ids
            else:
                id_set = set(ids)
                all_entity_ids = [eid for eid in all_entity_ids if eid in id_set]

        elif handler == "direct_user_match":
            # For FIWARE: post-fetch filter on owner attribute — not applicable
            # as entity ID filter; skip (executor handles post-filtering)
            pass

        else:
            logger.warning("Unknown FIWARE row filter handler: %s", handler)

    if all_entity_ids is not None and not all_entity_ids:
        return FiwareRowFilterResult(deny=True)

    return FiwareRowFilterResult(allowed_entity_ids=all_entity_ids)


class FiwareEntityFilterHandler:
    """Entry-point handler registered via dataset_api.row_filters."""

    name = "fiware_entity"

    async def resolve(
        self,
        *,
        table: str,
        user: AuthenticatedUser,
        args: dict[str, Any],
        request_context: dict[str, Any] | None = None,
    ):
        from celine.dataset.api.dataset_query.row_filters.models import RowFilterPlan

        urn_template = args.get("urn_template")
        if not urn_template:
            return RowFilterPlan(table=table, kind="allow")

        entity_ids = []
        device_id = args.get("device_id")
        if device_id:
            entity_ids.append(urn_template.replace("{device_id}", device_id))

        if not entity_ids:
            return RowFilterPlan(table=table, kind="allow")

        return RowFilterPlan(
            table=table,
            kind="allow",
            metadata={"entity_ids": entity_ids},
        )
