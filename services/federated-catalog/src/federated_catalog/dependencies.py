from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings


def get_settings_dep() -> Settings:
    return get_settings()


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


require_read_scope = require_scope("read_scope")
