"""Tell connectors their cached participant list is out of date.

A connector caches this registry for `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL`
because DSP-time membership checks run per negotiation and cannot each afford a
round trip. That is right for the hot path and wrong for a change an operator
just made: for up to the TTL the operator console shows a registry without the
participant they created, which is indistinguishable from the promote failing.

So a write that changes who is in the registry says so.

**Best-effort, always.** A promote is a durable state change that has already
committed; failing it because a cache hint could not be delivered would trade a
minute of staleness for a lost operation. Unreachable connectors are logged and
the cache expires on its own.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


async def invalidate_participant_caches(settings) -> None:
    """Ask every configured connector to drop its cached participant list."""
    urls = _connector_urls(settings)
    if not urls:
        return

    headers = {}
    try:
        headers["Authorization"] = f"Bearer {await _token(settings)}"
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        log.warning("No token for registry invalidation: %s", exc)
        return

    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in urls:
            target = f"{url.rstrip('/')}/internal/registry/invalidate"
            try:
                response = await client.post(target, headers=headers)
                response.raise_for_status()
                log.info("Invalidated participant cache at %s", url)
            except (httpx.HTTPError, httpx.RequestError) as exc:
                log.warning("Could not invalidate participant cache at %s: %s", url, exc)


def _connector_urls(settings) -> list[str]:
    """Connectors to notify, from `IDENTITY_REGISTRY_CONNECTOR_URLS`.

    A deployment is one participant with one connector, but provider and
    consumer roles run separate processes in development and both hold a cache,
    so this is a list rather than a single URL.
    """
    raw = getattr(settings, "connector_urls", "") or ""
    return [url.strip() for url in raw.split(",") if url.strip()]


_token_provider = None


async def _token(settings) -> str:
    """A service token carrying `connector.registry.invalidate`.

    Deliberately not `connector.internal`: that grant also reaches the subject
    pools behind `/internal/consent/check` and the data-plane signing keys
    behind `/internal/edr-jwks`, and a cache hint has no business with either.
    """
    global _token_provider
    if _token_provider is None:
        from ds_auth.service_token import ServiceTokenProvider

        if not settings.keycloak_token_url:
            raise RuntimeError("IDENTITY_REGISTRY_KEYCLOAK_TOKEN_URL is not set")
        _token_provider = ServiceTokenProvider(
            token_url=settings.keycloak_token_url,
            client_id=settings.service_client_id,
            client_secret=settings.service_client_secret,
        )
    return await _token_provider()
