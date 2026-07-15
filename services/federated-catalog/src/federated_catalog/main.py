"""ds-federated-catalog — FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request

from .cache import CatalogCache
from .config import get_settings
from .crawler import crawl_loop
from .dependencies import require_read_scope
from .metrics import install_metrics
from .api.catalog import router as catalog_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    cache = CatalogCache()

    app.state.cache = cache
    app.state.settings = settings

    if not settings.oidc_issuer_url:
        log.warning(
            "CATALOG_OIDC_ISSUER_URL is not set — "
            "JWT signature verification is DISABLED. "
            "This is acceptable for local development only."
        )
    else:
        import jwt

        jwks_url = f"{settings.oidc_issuer_url}/.well-known/openid-configuration"
        app.state.jwks_client = jwt.PyJWKClient(jwks_url)

    task = asyncio.create_task(crawl_loop(cache, settings))

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="ds-federated-catalog",
        description="Federated DCAT-AP catalog crawler for the dataspaces platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health(request: Request):
        cache = request.app.state.cache
        age = cache.cache_age_seconds
        return {
            "status": "ok",
            "version": "0.1.0",
            "cache_age_seconds": round(age, 1) if age is not None else None,
        }

    install_metrics(app, "ds-federated-catalog")

    app.include_router(
        catalog_router,
        dependencies=[Depends(require_read_scope)],
    )

    return app


app = create_app()
