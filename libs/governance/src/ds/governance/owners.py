"""Owner registry — lookup owners by id, alias, or URI.

Provides:
- ``OwnerEntry``: Pydantic model matching the identity-registry Owner schema.
- ``OwnersRegistry``: In-memory registry for tooling/CLI (loaded from YAML).
- ``load_owners_yaml``: Loads a YAML seed file into an ``OwnersRegistry``.
- ``HttpOwnersRegistry``: HTTP-backed async client with TTL cache (calls IR).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel

log = logging.getLogger(__name__)


class OwnerEntry(BaseModel, extra="ignore"):
    id: str
    type: str = "schema:Organization"
    name: str = ""
    did: str | None = None
    url: str | None = None
    aliases: list[str] = []
    organization_config: dict | None = None

    @property
    def canonical_uri(self) -> str | None:
        return self.did or self.url or None


class OwnersRegistry:
    """In-memory owner registry for tooling and CLI use."""

    def __init__(self, entries: list[OwnerEntry] | None = None):
        self._by_id: dict[str, OwnerEntry] = {}
        self._by_alias: dict[str, OwnerEntry] = {}
        for entry in entries or []:
            self._by_id[entry.id] = entry
            for alias in entry.aliases:
                self._by_alias[alias] = entry

    def by_id(self, owner_id: str) -> OwnerEntry | None:
        return self._by_id.get(owner_id) or self._by_alias.get(owner_id)

    def by_uri(self, uri: str) -> OwnerEntry | None:
        for entry in self._by_id.values():
            if entry.did == uri or entry.url == uri:
                return entry
        return None

    def canonical_uri(self, alias: str) -> str | None:
        entry = self.by_id(alias)
        return entry.canonical_uri if entry else None

    def all(self) -> list[OwnerEntry]:
        return list(self._by_id.values())


def load_owners_yaml(path: Path) -> OwnersRegistry:
    if not path.exists():
        return OwnersRegistry()
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    entries = [OwnerEntry(**e) for e in raw.get("owners", [])]
    return OwnersRegistry(entries)


class HttpOwnersRegistry:
    """Owner registry backed by identity-registry HTTP API with TTL cache."""

    def __init__(
        self,
        identity_registry_url: str,
        cache_ttl: float = 60.0,
        token_provider=None,
    ):
        self._base_url = identity_registry_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._cache: dict[str, OwnerEntry] = {}
        self._cache_times: dict[str, float] = {}
        self._token_provider = token_provider
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=10.0
        )

    async def _get_headers(self) -> dict[str, str]:
        if self._token_provider:
            token = await self._token_provider()
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def _resolve(self, alias: str) -> OwnerEntry | None:
        now = time.monotonic()
        cached = self._cache.get(alias)
        cache_time = self._cache_times.get(alias, 0.0)
        if cached is not None and (now - cache_time) < self._cache_ttl:
            return cached

        try:
            headers = await self._get_headers()
            resp = await self._client.get(
                "/owners/resolve", params={"alias": alias}, headers=headers
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            entry = OwnerEntry(**resp.json())
            self._cache[alias] = entry
            self._cache_times[alias] = now
            return entry
        except httpx.HTTPError as exc:
            log.error("Failed to resolve owner '%s': %s", alias, exc)
            return cached

    async def canonical_uri(self, alias: str) -> str | None:
        entry = await self._resolve(alias)
        return entry.canonical_uri if entry else None

    async def by_id(self, alias: str) -> OwnerEntry | None:
        return await self._resolve(alias)

    async def close(self) -> None:
        await self._client.aclose()
