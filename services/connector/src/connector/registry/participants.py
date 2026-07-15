"""Participant registry — backed by identity-registry HTTP API or static YAML."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Participant(BaseModel):
    id: str
    dsp_address: str
    allowed_scopes: list[str] = []
    role: str = "consumer"


class UnknownParticipantError(ValueError):
    pass


class ParticipantRegistry:
    def __init__(self, participants: list[Participant]):
        self._by_id: dict[str, Participant] = {p.id: p for p in participants}
        self._by_dsp: dict[str, Participant] = {
            p.dsp_address: p for p in participants if p.dsp_address
        }

    @classmethod
    def from_file(cls, path: Path) -> ParticipantRegistry:
        if not path.exists():
            return cls([])
        with path.open("r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        participants = [
            Participant.model_validate(p)
            for p in (raw.get("participants") or [])
        ]
        return cls(participants)

    @classmethod
    def empty(cls) -> ParticipantRegistry:
        return cls([])

    def validate(self, counter_party_address: str) -> Participant:
        """Return participant by DSP address; raise if not registered."""
        p = self._by_dsp.get(counter_party_address)
        if p is None:
            raise UnknownParticipantError(
                f"Participant with DSP address '{counter_party_address}' is not registered"
            )
        return p

    def get_by_id(self, participant_id: str) -> Participant | None:
        return self._by_id.get(participant_id)

    def all(self) -> list[Participant]:
        return list(self._by_id.values())


class HttpParticipantRegistry:
    """Participant registry backed by identity-registry HTTP API with TTL cache."""

    def __init__(self, identity_registry_url: str, cache_ttl: float = 60.0):
        self._base_url = identity_registry_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._cache: ParticipantRegistry | None = None
        self._cache_time: float = 0.0
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=10.0
        )

    async def _refresh_cache(self) -> ParticipantRegistry:
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache
        try:
            resp = await self._client.get("/admin/participants")
            resp.raise_for_status()
            data = resp.json()
            participants = [
                Participant(
                    id=p["did"],
                    dsp_address=p.get("dsp_address") or "",
                    allowed_scopes=p.get("allowed_scopes", []),
                    role=p.get("role", "consumer"),
                )
                for p in data
            ]
            self._cache = ParticipantRegistry(participants)
            self._cache_time = now
        except httpx.HTTPError as exc:
            log.error("Failed to fetch participants from identity-registry: %s", exc)
            if self._cache is not None:
                return self._cache
            self._cache = ParticipantRegistry.empty()
            self._cache_time = now
        return self._cache

    async def validate(self, counter_party_address: str) -> Participant:
        registry = await self._refresh_cache()
        return registry.validate(counter_party_address)

    async def get_by_id(self, participant_id: str) -> Participant | None:
        registry = await self._refresh_cache()
        return registry.get_by_id(participant_id)

    async def all(self) -> list[Participant]:
        registry = await self._refresh_cache()
        return registry.all()

    async def check_scope(self, participant_id: str, scope: str) -> bool:
        """Forward scope check to identity-registry for authoritative answer."""
        try:
            resp = await self._client.get(
                "/admin/participants/check",
                params={"did": participant_id, "scope": scope},
            )
            resp.raise_for_status()
            return resp.json().get("allowed", False)
        except httpx.HTTPError as exc:
            log.error("Scope check failed for %s: %s", participant_id, exc)
            return False

    async def close(self) -> None:
        await self._client.aclose()
