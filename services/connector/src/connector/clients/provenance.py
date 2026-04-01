"""Async httpx client for the ds-provenance service."""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ProvenanceClient:
    def __init__(self, base_url: str):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def emit_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """POST a domain event to /prov/events. Non-fatal on failure."""
        try:
            r = await self._http.post("/prov/events", json=event)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning("Failed to emit provenance event: %s", exc)
            return None

    async def get_lineage(self, iri: str, direction: str = "both") -> dict[str, Any] | None:
        try:
            from urllib.parse import quote
            r = await self._http.get(
                f"/prov/lineage/{quote(iri, safe='')}",
                params={"direction": direction},
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning("Failed to fetch lineage for %s: %s", iri, exc)
            return None
