"""Outgoing service-to-service authentication via Keycloak client_credentials.

Requires ``httpx``: available in every service that depends on ds-auth.

Usage::

    from ds_auth.service_token import ServiceTokenProvider

    token_provider = ServiceTokenProvider(
        token_url="http://keycloak:8080/realms/dataspaces/protocol/openid-connect/token",
        client_id="svc-ds-connector",
        client_secret="svc-ds-connector",
    )

    # Pass as callback to registry clients that accept a token_provider
    owners = HttpOwnersRegistry(ir_url, token_provider=token_provider)

    # Or call directly
    token = await token_provider()
"""
from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)


class ServiceTokenProvider:
    """Acquires and caches a Keycloak service token via client_credentials grant."""

    def __init__(self, token_url: str, client_id: str, client_secret: str):
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def __call__(self) -> str:
        now = time.monotonic()
        if self._token and now < self._expires_at:
            return self._token

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        self._token = data["access_token"]
        self._expires_at = now + data.get("expires_in", 300) - 30
        log.debug("Acquired service token for %s (expires in %ds)", self._client_id, data.get("expires_in", 300))
        return self._token
