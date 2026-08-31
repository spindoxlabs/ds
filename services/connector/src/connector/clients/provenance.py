"""Async httpx client for the ds-provenance service."""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ProvenanceClient:
    def __init__(self, base_url: str, token_provider=None):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._token_provider = token_provider

    async def _auth_headers(self) -> dict[str, str]:
        if self._token_provider:
            token = await self._token_provider()
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def close(self) -> None:
        await self._http.aclose()

    async def emit_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """POST a domain event to /prov/events. Non-fatal on failure."""
        try:
            headers = await self._auth_headers()
            r = await self._http.post("/prov/events", json=event, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning("Failed to emit provenance event: %s", exc)
            return None

    # This client writes; it does not read. `get_lineage` was the only read
    # method and had no caller — nothing in the connector consumes lineage. It
    # would not have worked either: `svc-ds-connector` holds `provenance.write`
    # and **not** `provenance.read` (provenance row `L-13`), so every call would
    # have 403'd into the `except` and returned `None`, indistinguishable from a
    # node with no lineage. Restoring it means granting the scope first.
