from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db.engine import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


def get_settings_dep() -> Settings:
    return get_settings()


async def require_admin_scope(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth_header.removeprefix("Bearer ").strip()

    if settings.oidc_issuer_url:
        import jwt

        try:
            jwks_client = request.app.state.jwks_client
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    else:
        import jwt

        try:
            claims = jwt.decode(
                token, options={"verify_signature": False}
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    scopes = claims.get("scope", "").split()
    if settings.admin_scope not in scopes:
        raise HTTPException(
            status_code=403,
            detail=f"Missing required scope: {settings.admin_scope}",
        )

    return claims
