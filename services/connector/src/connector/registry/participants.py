"""Participant registry — backed by identity-registry HTTP API or static YAML."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Participant(BaseModel):
    id: str
    dsp_address: str
    allowed_scopes: list[str] = []
    roles: list[str] = ["consumer"]


class UnknownParticipantError(ValueError):
    pass


class ParticipantLookup(Protocol):
    """What a consumer needs of a participant registry — either implementation.

    There are two, and they are **not** related by inheritance: `ParticipantRegistry`
    reads a file and answers synchronously; `HttpParticipantRegistry` asks the
    identity-registry and answers with a coroutine. `ConsumerService` bridges them
    at the call — `await result if inspect.isawaitable(result) else result` — so it
    genuinely accepts both, and the union return type here is that fact rather than
    a widening for the checker's benefit.

    It was typed as `ParticipantRegistry` and handed the HTTP one, which type-checked
    as three separate errors in `main.py` and would have misled anyone reading the
    signature to call `validate` without awaiting it.
    """

    def validate(
        self, counter_party_address: str
    ) -> Participant | Awaitable[Participant]: ...


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
            Participant.model_validate(p) for p in (raw.get("participants") or [])
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
                f"Participant with DSP address '{counter_party_address}' "
                "is not registered"
            )
        return p

    def get_by_id(self, participant_id: str) -> Participant | None:
        return self._by_id.get(participant_id)

    def all(self) -> list[Participant]:
        return list(self._by_id.values())


class HttpParticipantRegistry:
    """Participant registry backed by identity-registry HTTP API with TTL cache."""

    def __init__(
        self,
        identity_registry_url: str,
        cache_ttl: float = 60.0,
        token_provider=None,
        max_staleness_factor: float = 5.0,
    ):
        self._base_url = identity_registry_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._max_staleness = max(cache_ttl * max_staleness_factor, 300.0)
        self._cache: ParticipantRegistry | None = None
        self._cache_time: float = 0.0
        self._last_success: float = 0.0
        self._token_provider = token_provider
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def _get_headers(self) -> dict[str, str]:
        if self._token_provider:
            token = await self._token_provider()
            return {"Authorization": f"Bearer {token}"}
        return {}

    def invalidate(self) -> None:
        """Drop the cache so the next read comes from the identity-registry.

        Called when something is known to have changed — a participant promoted,
        suspended or revoked. Without it the registry is eventually consistent on
        a 60s timer, which is right for the DSP-time membership checks this cache
        exists for and wrong for an operator who has just created a participant
        and is looking at a list that does not contain it. They cannot tell that
        from a failure.
        """
        self._cache = None
        self._cache_time = 0.0

    async def _refresh_cache(self, *, force: bool = False) -> ParticipantRegistry:
        now = time.monotonic()
        if (
            not force
            and self._cache is not None
            and (now - self._cache_time) < self._cache_ttl
        ):
            return self._cache
        try:
            headers = await self._get_headers()
            resp = await self._client.get("/admin/participants", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            participants = [
                Participant(
                    id=p["did"],
                    dsp_address=p.get("dsp_address") or "",
                    allowed_scopes=p.get("allowed_scopes", []),
                    roles=p.get("roles", [p.get("role", "consumer")]),
                )
                for p in data
            ]
            self._cache = ParticipantRegistry(participants)
            self._cache_time = now
            self._last_success = now
        except httpx.HTTPError as exc:
            log.error("Failed to fetch participants from identity-registry: %s", exc)
            if self._cache is not None:
                staleness = now - self._last_success
                if self._last_success > 0 and staleness > self._max_staleness:
                    raise UnknownParticipantError(
                        f"Identity-registry unreachable for {staleness:.0f}s "
                        f"(max {self._max_staleness:.0f}s) — refusing stale "
                        "participant data"
                    ) from exc
                log.warning(
                    "Serving stale participant cache (age %.0fs, max %.0fs)",
                    staleness,
                    self._max_staleness,
                )
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

    async def all(self, *, fresh: bool = False) -> list[Participant]:
        """Every known participant.

        `fresh=True` bypasses the cache. Used by the operator's own view, which
        is read a few times a minute by a person who may have just changed
        something — unlike the negotiation-time checks this cache is for, which
        run per DSP request and can tolerate a minute of lag.
        """
        registry = await self._refresh_cache(force=fresh)
        return registry.all()

    async def check_scope(self, participant_id: str, scope: str) -> bool:
        """Forward scope check to identity-registry for authoritative answer."""
        try:
            headers = await self._get_headers()
            resp = await self._client.get(
                "/admin/participants/check",
                params={"did": participant_id, "scope": scope},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("allowed", False)
        except httpx.HTTPError as exc:
            log.error("Scope check failed for %s: %s", participant_id, exc)
            return False

    async def close(self) -> None:
        await self._client.aclose()
