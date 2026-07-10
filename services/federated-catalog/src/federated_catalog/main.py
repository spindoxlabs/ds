"""ds-federated-catalog — FastAPI application factory."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .cache import CatalogCache
from .config import get_settings
from .crawler import crawl_loop
from .metrics import install_metrics
from .api.catalog import router as catalog_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    cache = CatalogCache()

    app.state.cache = cache
    app.state.settings = settings

    # Start background crawler
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

    app.include_router(catalog_router)

    return app


app = create_app()
