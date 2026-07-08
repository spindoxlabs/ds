from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from dataset_api_fiware.schemas import AggrMethod, AggrPeriod, FiwareQueryModel

logger = logging.getLogger(__name__)


class QuantumLeapClient:
    def __init__(
        self,
        base_url: str,
        fiware_service: str,
        fiware_service_path: str | None = None,
        timeout_ms: int = 10000,
    ):
        self.base_url = base_url.rstrip("/")
        self.fiware_service = fiware_service
        self.fiware_service_path = fiware_service_path
        self.timeout = timeout_ms / 1000.0

    def _headers(self, user_token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"fiware-Service": self.fiware_service}
        if self.fiware_service_path:
            headers["fiware-ServicePath"] = self.fiware_service_path
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        return headers

    def _query_params(
        self,
        query: FiwareQueryModel,
        entity_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if query.from_date:
            params["fromDate"] = query.from_date.isoformat()
        if query.to_date:
            params["toDate"] = query.to_date.isoformat()
        if query.aggr_method:
            params["aggrMethod"] = query.aggr_method.value
        if query.aggr_period:
            params["aggrPeriod"] = query.aggr_period.value
        if query.limit:
            params["limit"] = query.limit
        if query.offset:
            params["offset"] = query.offset
        if query.last_n:
            params["lastN"] = query.last_n
        if entity_ids:
            params["id"] = ",".join(entity_ids)
        if query.attrs:
            params["attrs"] = ",".join(query.attrs)
        return params

    def _select_endpoint(
        self,
        query: FiwareQueryModel,
    ) -> tuple[str, bool, bool, bool]:
        """Select QL endpoint based on query shape.

        Returns (url_path, is_single_entity, is_multi_entity, is_entities_list).
        """
        single_entity = query.entity_id is not None
        single_attr = query.attrs is not None and len(query.attrs) == 1

        if single_entity and single_attr:
            attr = query.attrs[0]
            return (
                f"/v2/entities/{query.entity_id}/attrs/{attr}",
                True, False, False,
            )
        if single_entity:
            return (
                f"/v2/entities/{query.entity_id}",
                True, False, False,
            )
        if single_attr:
            attr = query.attrs[0]
            return (
                f"/v2/types/{query.entity_type}/attrs/{attr}",
                False, True, False,
            )
        return (
            f"/v2/types/{query.entity_type}",
            False, True, False,
        )

    async def query(
        self,
        query: FiwareQueryModel,
        *,
        entity_ids: list[str] | None = None,
        user_token: str | None = None,
    ) -> tuple[Any, bool, bool, bool]:
        """Execute a QL query. Returns (data, is_single, is_multi, is_list)."""
        path, is_single, is_multi, is_list = self._select_endpoint(query)
        url = f"{self.base_url}{path}"
        params = self._query_params(query, entity_ids=entity_ids)
        headers = self._headers(user_token)

        logger.debug("QL request: %s params=%s", url, params)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=headers)

            if resp.status_code == 404:
                return [], False, False, True

            if 400 <= resp.status_code < 500:
                logger.warning("QL 4xx: %s %s", resp.status_code, resp.text[:200])
                raise HTTPException(400, f"QuantumLeap query error: {resp.status_code}")

            if resp.status_code >= 500:
                logger.error("QL 5xx: %s %s", resp.status_code, resp.text[:200])
                raise HTTPException(502, "QuantumLeap server error")

            resp.raise_for_status()
            return resp.json(), is_single, is_multi, is_list

        except HTTPException:
            raise
        except httpx.RequestError as exc:
            logger.error("QL unreachable: %s", exc)
            raise HTTPException(502, "QuantumLeap unreachable") from exc

    async def list_entities(
        self,
        entity_type: str,
        *,
        user_token: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List entities of a given type (last-value)."""
        url = f"{self.base_url}/v2/entities"
        params: dict[str, Any] = {
            "type": entity_type,
            "limit": limit,
            "offset": offset,
        }
        headers = self._headers(user_token)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=headers)

            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return resp.json()

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise HTTPException(502, "QuantumLeap server error") from exc
            raise HTTPException(400, f"QuantumLeap error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise HTTPException(502, "QuantumLeap unreachable") from exc
