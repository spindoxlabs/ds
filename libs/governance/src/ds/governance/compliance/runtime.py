"""Runtime registry lookups — validate against a live identity-registry.

Lets the same checks run either offline (YAML seeds, for CI and pre-commit) or
against a deployment (for a pre-import gate in staging/production), by
satisfying the ``OwnerLookup`` protocol from either source.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..owners import OwnerEntry

log = logging.getLogger(__name__)


class RuntimeOwnerLookup:
    """``OwnerLookup`` backed by a live identity-registry.

    Resolves aliases lazily via ``GET /owners/resolve`` and caches results, so
    validating N datasets costs at most one call per distinct alias.
    """

    def __init__(
        self,
        identity_registry_url: str,
        *,
        token: str | None = None,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = identity_registry_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._cache: dict[str, OwnerEntry | None] = {}
        self._listed: list[OwnerEntry] | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> RuntimeOwnerLookup:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def by_id(self, owner_id: str) -> OwnerEntry | None:
        if owner_id in self._cache:
            return self._cache[owner_id]
        entry: OwnerEntry | None = None
        try:
            resp = self._client.get(
                f"{self._base_url}/owners/resolve",
                params={"alias": owner_id},
                headers=self._headers,
            )
            if resp.status_code != 404:
                resp.raise_for_status()
                entry = OwnerEntry(**resp.json())
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Failed to resolve owner '{owner_id}' against {self._base_url}: {exc}"
            ) from exc
        self._cache[owner_id] = entry
        return entry

    def all(self) -> list[OwnerEntry]:
        """List every owner. Requires an admin token; degrades to what was resolved."""
        if self._listed is not None:
            return self._listed
        try:
            resp = self._client.get(
                f"{self._base_url}/admin/owners", headers=self._headers
            )
            resp.raise_for_status()
            self._listed = [OwnerEntry(**item) for item in resp.json()]
        except httpx.HTTPError as exc:
            log.warning(
                "Cannot list owners from %s (%s) — falling back to resolved aliases only",
                self._base_url,
                exc,
            )
            self._listed = [entry for entry in self._cache.values() if entry]
        return self._listed


def fetch_participant_roles(
    identity_registry_url: str,
    *,
    token: str | None = None,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> dict[str, list[str]] | None:
    """Fetch ``did -> roles`` for every participant. Returns None if unavailable.

    Used to validate an offer's ``controller_role`` against the roles the
    controller actually holds — a participant can act in several capacities
    (a DSO's grid-operations and metering functions are distinct controllers),
    and only the declared ones may appear in an offer.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(
            f"{identity_registry_url.rstrip('/')}/participants", headers=headers
        )
        resp.raise_for_status()
        return {
            item["did"]: list(item.get("roles") or [])
            for item in resp.json()
            if isinstance(item, dict) and item.get("did")
        }
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning(
            "Cannot list participant roles from %s (%s) — skipping controller-role check",
            identity_registry_url,
            exc,
        )
        return None
    finally:
        if owns_client:
            client.close()


def fetch_participant_dids(
    identity_registry_url: str,
    *,
    token: str | None = None,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> set[str] | None:
    """Fetch registered participant DIDs. Returns None if unavailable."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(
            f"{identity_registry_url.rstrip('/')}/participants", headers=headers
        )
        resp.raise_for_status()
        return {
            item["did"]
            for item in resp.json()
            if isinstance(item, dict) and item.get("did")
        }
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning(
            "Cannot list participants from %s (%s) — skipping owner-participant check",
            identity_registry_url,
            exc,
        )
        return None
    finally:
        if owns_client:
            client.close()
