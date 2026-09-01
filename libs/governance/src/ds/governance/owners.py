"""Owner registry — the shared shape from upstream, ds's live resolution on top.

**The record and the in-memory registry are `celine.governance.owners`'** — phase 4
of `ADR-0013`. There were five copies of them before that module consolidated them
(`celine-utils`, `dataset-api`, `celine-superset`, `celine-policies`, ds), and its
docstring names what ds's copy got wrong rather than leaving it to be rediscovered:

- **The Keycloak block was named after a database column.** ds declared
  `organization_config`, which is the identity-registry's column and therefore the
  key in its API responses — but `owners.yaml` says `organization`. So the model
  read an IR response correctly and **silently dropped the block when loading a
  YAML**, which is the only place a human writes it. `services/identity-registry`
  passes those files to `OwnerEntry(**entry)` when it decides which organisations
  to onboard. Upstream declares `organization` with an `AliasChoices` accepting
  both, so one model reads both sources.
- **Ids and aliases shared one map**, so an alias could shadow an owner id
  depending on file order, and nothing said so. Upstream keeps them apart, gives
  ids precedence, and warns on a collision.
- **`by_uri` was a linear scan** over every entry on every call.

Provides here:

- ``HttpOwnersRegistry``: HTTP-backed async client with TTL cache (calls IR).

Re-exported, defined upstream:

- ``OwnerEntry``, ``OwnersRegistry``, ``load_owners_yaml``.

`HttpOwnersRegistry` stays, and the split is the same one the whole ADR draws:
the *shape* of an owner is the ecosystem's, while resolving an alias against a
live identity registry — with a token provider, a TTL cache and a fallback to the
last good answer — is ds's concern and nobody else's.

**One behaviour changes, deliberately: a missing owners file now raises.** ds's
loader returned an empty registry; upstream's raises `FileNotFoundError` unless the
caller passes `missing_ok=True`, and it takes that parameter precisely because the
two implementations disagreed. ds takes the raise, because the empty registry is
the `CI-02` shape and this repository has the receipts for it —
`resolver.from_file` deleted the same behaviour twice, most recently after every
`task dev:*` provider had run with no governance at all, starting clean and logging
nothing. The one caller is `cli.py`, and it passes a path only when `--owners` named
one; an owners file that was asked for and is not there would otherwise leave every
owner check resolving nothing and reporting a pass it did not make — which is
exactly what the CLI already refuses to do for `--identity-registry-url`.
"""

from __future__ import annotations

import logging
import time

import httpx

# Re-exported under their own names — `X as X` is the explicit-re-export form, and
# it is what tells a linter these are the module's public surface rather than dead
# imports. `ds.governance.OwnerEntry` is imported by `services/identity-registry`
# and by `compliance/runtime.py`; keeping the names here means neither changed.
from celine.governance.owners import OwnerEntry as OwnerEntry
from celine.governance.owners import OwnerOrganization as OwnerOrganization
from celine.governance.owners import OwnersRegistry as OwnersRegistry
from celine.governance.owners import load_owners_yaml as load_owners_yaml

log = logging.getLogger(__name__)


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
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

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
