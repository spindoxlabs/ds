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
from ds_auth.production import ProductionGuard
from ds_auth.service_token import ServiceTokenProvider

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    cache = CatalogCache()

    app.state.cache = cache
    app.state.settings = settings

    guard = ProductionGuard("ds-federated-catalog")
    guard.require_set(
        "CATALOG_OIDC_ISSUER_URL",
        settings.oidc_issuer_url,
        "Point at the Keycloak realm issuer so JWT signatures are verified.",
    )
    guard.forbid_true(
        "CATALOG_OIDC_INSECURE_DEV",
        settings.oidc_insecure_dev,
        "Set CATALOG_OIDC_INSECURE_DEV=false and configure the issuer URL.",
    )
    guard.forbid_default(
        "CATALOG_SERVICE_CLIENT_SECRET",
        settings.service_client_secret,
        {"svc-ds-federated-catalog"},
        "Set the Keycloak client secret for svc-ds-federated-catalog.",
    )
    guard.enforce()

    ir_token_provider = ServiceTokenProvider(
        token_url=settings.keycloak_token_url,
        client_id=settings.service_client_id,
        client_secret=settings.service_client_secret,
    )

    task = asyncio.create_task(crawl_loop(cache, settings, token_provider=ir_token_provider))

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ds-federated-catalog",
        description="Federated DCAT-AP catalog crawler for the dataspaces platform",
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
