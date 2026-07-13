from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.v1.admin import router as admin_router
from .api.v1.internal import router as internal_router
from .api.v1.public import router as public_router
from .config import get_settings
from .db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    settings = get_settings()
    if settings.oidc_issuer_url:
        import jwt

        jwks_url = f"{settings.oidc_issuer_url}/.well-known/openid-configuration"
        app.state.jwks_client = jwt.PyJWKClient(jwks_url)

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ds-identity-registry",
        description="DID lifecycle, VC issuance, participant registry, StatusList2021",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(public_router)
    app.include_router(internal_router)
    app.include_router(admin_router)

    return app


app = create_app()
