"""FastAPI dependency providers for ds-connector."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db.engine import get_session_factory

log = logging.getLogger(__name__)


def get_settings_dep() -> Settings:
    return get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


def get_provider_edc(request: Request):
    return request.app.state.provider_edc


def get_consumer_edc(request: Request):
    return request.app.state.consumer_edc


def get_consumer_service(request: Request):
    return request.app.state.consumer_service


def get_participant_registry(request: Request):
    return request.app.state.registry


def get_notifier(request: Request):
    return request.app.state.notifier


# ── JWT auth ──────────────────────────────────────────────────────────────


async def _decode_jwt(request: Request, settings: Settings) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth_header.removeprefix("Bearer ").strip()

    import jwt

    if settings.oidc_issuer_url:
        try:
            jwks_client = request.app.state.jwks_client
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.service_client_id,
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    else:
        try:
            claims = jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    return claims


def require_scope(*scope_attrs: str) -> Callable:
    """Factory: returns a dependency that requires at least one of the named scopes.

    Each *scope_attr* is an attribute name on ``Settings``
    (e.g. ``"admin_scope"``, ``"internal_scope"``).
    """

    async def _dependency(
        request: Request,
        settings: Settings = Depends(get_settings_dep),
    ) -> dict:
        claims = await _decode_jwt(request, settings)
        token_scopes = claims.get("scope", "").split()
        required = [getattr(settings, attr) for attr in scope_attrs]
        if not any(s in token_scopes for s in required):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope: {' or '.join(required)}",
            )
        return claims

    return _dependency


require_admin_scope = require_scope("admin_scope")
require_internal_scope = require_scope("internal_scope")
require_webhook_scope = require_scope("webhook_scope")
