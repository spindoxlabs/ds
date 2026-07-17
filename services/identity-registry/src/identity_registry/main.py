from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.v1.admin import router as admin_router
from .api.v1.credentials import router as credentials_router
from .api.v1.memberships import router as memberships_router
from .api.v1.owners import router as owners_router
from .api.v1.public import router as public_router
from .api.v1.sts import router as sts_router
from .api.v1.users import router as users_router
from .config import get_settings
from .db.engine import init_db

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    settings = get_settings()

    if not settings.oidc_issuer_url:
        log.warning(
            "IDENTITY_REGISTRY_OIDC_ISSUER_URL is not set — "
            "JWT signature verification is DISABLED. "
            "This is acceptable for local development only."
        )

    if settings.encryption_key == "dev-encryption-key-change-in-production":
        log.warning(
            "IDENTITY_REGISTRY_ENCRYPTION_KEY is set to the default dev value — "
            "private keys are NOT securely encrypted. "
            "Set a strong Fernet key for production."
        )

    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ds-identity-registry",
        description="DID lifecycle, VC issuance, participant registry, StatusList2021",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Auth config is static and must be available even without lifespan (tests).
    from ds_auth import OidcConfig

    app.state.oidc_config = OidcConfig(
        issuer_url=settings.oidc_issuer_url,
        audience=settings.service_client_id,
        insecure_dev=settings.oidc_insecure_dev,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(public_router)
    app.include_router(sts_router)
    app.include_router(credentials_router)
    app.include_router(admin_router)
    app.include_router(memberships_router)
    app.include_router(owners_router)
    app.include_router(users_router)

    return app


app = create_app()
