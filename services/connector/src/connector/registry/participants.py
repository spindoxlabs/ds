"""Participant registry — backed by identity-registry HTTP API or static YAML."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
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


class CollectorLookupError(RuntimeError):
    """The registry could not say whether an organisation is an accepted collector.

    Distinct from "not accepted": that is an answer, and the route refuses with
    a 403. This is the absence of one, and the route answers 503 — never an
    acceptance (fail closed), never a 403 that files a permanent failure for an
    outage.
    """


@dataclass(frozen=True)
class CollectorAnswer:
    """May *collector* register consent at *holder*, and for whose members?

    ``collector_owner`` is the owner id the collector's DID belongs to — what a
    subject's membership is checked against (`D-21`). ``None`` when no single
    owner carries that DID.
    """

    accepted: bool
    collector_owner: str | None
    reason: str


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
    def __init__(
        self,
        participants: list[Participant],
        collectors: list[dict[str, Any]] | None = None,
    ):
        self._by_id: dict[str, Participant] = {p.id: p for p in participants}
        self._by_dsp: dict[str, Participant] = {
            p.dsp_address: p for p in participants if p.dsp_address
        }
        #: `(holder_did, collector_did)` → the collector's owner id. The static
        #: form of the registry relation, for a deployment with no registry.
        self._collectors: dict[tuple[str, str], str | None] = {
            (str(c["holder_did"]), str(c["collector_did"])): c.get("collector_owner")
            for c in (collectors or [])
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
        return cls(participants, collectors=raw.get("consent_collectors") or [])

    def consent_collector(self, holder_did: str, collector_did: str) -> CollectorAnswer:
        """The static relation. A holder always collects for itself."""
        if (holder_did, collector_did) in self._collectors:
            return CollectorAnswer(
                True,
                self._collectors[(holder_did, collector_did)],
                "an accepted collector",
            )
        if holder_did == collector_did:
            return CollectorAnswer(True, None, "a holder collects for itself")
        return CollectorAnswer(False, None, "not an accepted collector")

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
    """Participant registry backed by identity-registry HTTP API with TTL cache.

    **Two reads, two routes.** "Who is this one counterparty?" — `validate` and
    `get_by_id`, asked on every consumer request (rulebook `C-19`) — goes to
    `GET /participants/resolve`, which answers for one active participant with
    its DID, DSP address and roles and nothing else. The connector's
    organisation client reaches it on `identity-registry.read`. It used to read
    the whole `GET /admin/participants` listing, scopes included, for that.

    The listing stays for what genuinely needs the listing: the operator view
    (`all`).

    **There is no `check_scope` any more.** It forwarded to the anchor's
    `GET /admin/participants/check` so that `AccessScopeFunction` could ask, per
    negotiation, whether a string was in a participant's `allowed_scopes`. The
    string granted nothing, the anchor could not keep it in step with the
    `MembershipCredential` it signs, and the claim was already in the verifier's
    hands — so membership is read off that credential now
    (`the-owner-scope-is-a-string-nobody-grants`). The anchor's route survives
    for an operator asking about a grant; nothing in the exchange path calls it.
    """

    def __init__(
        self,
        identity_registry_url: str,
        cache_ttl: float = 60.0,
        token_provider=None,
        max_staleness_factor: float = 5.0,
        collector_cache_ttl: float | None = None,
    ):
        self._base_url = identity_registry_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._max_staleness = max(cache_ttl * max_staleness_factor, 300.0)
        #: The collector relation's own TTL (`CONNECTOR_COLLECTOR_CACHE_TTL`).
        #: Its staleness bound scales with it, so a deployment that shortens the
        #: TTL to see revocations sooner also shortens how long an outage can
        #: serve an old acceptance.
        self._collector_ttl = (
            cache_ttl if collector_cache_ttl is None else collector_cache_ttl
        )
        self._collector_max_staleness = max(
            self._collector_ttl * max_staleness_factor, self._collector_ttl
        )
        #: `(holder, collector)` → `(answer, fetched_at)`.
        self._collectors: dict[tuple[str, str], tuple[CollectorAnswer, float]] = {}
        self._cache: ParticipantRegistry | None = None
        self._cache_time: float = 0.0
        self._last_success: float = 0.0
        self._token_provider = token_provider
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)
        #: `(key, value)` → `(participant or None, fetched_at)`.
        self._resolved: dict[tuple[str, str], tuple[Participant | None, float]] = {}

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
        self._resolved.clear()
        # The identity-registry sends the same hint when a collector relation
        # changes, so a revoked collector stops being accepted now, not at TTL.
        self._collectors.clear()

    async def _resolve(self, key: str, value: str) -> Participant | None:
        """One participant, by `did` or `dsp_address`; `None` if not registered.

        Cached per key for `cache_ttl`, a miss included — `invalidate()` is what
        makes a just-promoted participant visible sooner. On an outage a cached
        answer is served until `max_staleness`; past that, or with nothing
        cached, the lookup **fails closed** with `UnknownParticipantError`
        rather than reading as "not registered".
        """
        now = time.monotonic()
        cached = self._resolved.get((key, value))
        if cached is not None and (now - cached[1]) < self._cache_ttl:
            return cached[0]
        try:
            headers = await self._get_headers()
            resp = await self._client.get(
                "/participants/resolve", params={key: value}, headers=headers
            )
            if resp.status_code == 404:
                participant = None
            else:
                resp.raise_for_status()
                data = resp.json()
                participant = Participant(
                    id=data["did"],
                    dsp_address=data.get("dsp_address") or "",
                    roles=list(data.get("roles") or []),
                )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.error("Participant lookup %s=%s failed: %s", key, value, exc)
            if cached is not None and (now - cached[1]) <= self._max_staleness:
                log.warning(
                    "Serving stale participant lookup (age %.0fs, max %.0fs)",
                    now - cached[1],
                    self._max_staleness,
                )
                return cached[0]
            raise UnknownParticipantError(
                f"Identity-registry could not answer for {key}={value!r}; "
                "refusing to treat the counterparty as registered"
            ) from exc
        self._resolved[(key, value)] = (participant, now)
        return participant

    async def consent_collector(
        self, holder_did: str, collector_did: str
    ) -> CollectorAnswer:
        """Ask `GET /consent-collectors/check`, cached per pair.

        Same shape as `_resolve`: cached for the collector TTL, a refusal
        included; on an outage a cached answer is served until the staleness
        bound; past that, or with nothing cached, `CollectorLookupError` — which
        the route turns into a 503, never an acceptance.
        """
        now = time.monotonic()
        key = (holder_did, collector_did)
        cached = self._collectors.get(key)
        if cached is not None and (now - cached[1]) < self._collector_ttl:
            return cached[0]
        try:
            headers = await self._get_headers()
            resp = await self._client.get(
                "/consent-collectors/check",
                params={"holder_did": holder_did, "collector_did": collector_did},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            accepted = data["accepted"]
            if not isinstance(accepted, bool):
                raise ValueError(f"'accepted' is not a boolean: {accepted!r}")
            answer = CollectorAnswer(
                accepted=accepted,
                collector_owner=data.get("collector_owner"),
                reason=str(data.get("reason") or ""),
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.error(
                "Collector lookup %s → %s failed: %s", collector_did, holder_did, exc
            )
            if (
                cached is not None
                and (now - cached[1]) <= self._collector_max_staleness
            ):
                log.warning(
                    "Serving stale collector lookup (age %.0fs, max %.0fs)",
                    now - cached[1],
                    self._collector_max_staleness,
                )
                return cached[0]
            raise CollectorLookupError(
                f"identity-registry could not say whether {collector_did} may "
                f"register consent at {holder_did}"
            ) from exc
        self._collectors[key] = (answer, now)
        return answer

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
        participant = await self._resolve("dsp_address", counter_party_address)
        if participant is None:
            raise UnknownParticipantError(
                f"Participant with DSP address '{counter_party_address}' "
                "is not registered"
            )
        return participant

    async def get_by_id(self, participant_id: str) -> Participant | None:
        return await self._resolve("did", participant_id)

    async def all(self, *, fresh: bool = False) -> list[Participant]:
        """Every known participant.

        `fresh=True` bypasses the cache. Used by the operator's own view, which
        is read a few times a minute by a person who may have just changed
        something — unlike the negotiation-time checks this cache is for, which
        run per DSP request and can tolerate a minute of lag.
        """
        registry = await self._refresh_cache(force=fresh)
        return registry.all()

    async def close(self) -> None:
        await self._client.aclose()
