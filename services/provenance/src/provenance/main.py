"""ds-provenance — FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import get_settings
from .db.engine import init_db
from .schemas.context import PROV_CONTEXT
from .api.v1.nodes import router as nodes_router
from .api.v1.relations import router as relations_router
from .api.v1.events import router as events_router
from .api.v1.lineage import router as lineage_router
from .api.v1.audit import router as audit_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ds-provenance",
        description="W3C PROV-O compatible provenance service",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/prov/context", response_class=JSONResponse)
    async def context():
        return JSONResponse(
            content={"@context": PROV_CONTEXT},
            media_type="application/ld+json",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    app.include_router(nodes_router, prefix="/prov")
    app.include_router(relations_router, prefix="/prov")
    app.include_router(events_router, prefix="/prov")
    app.include_router(lineage_router, prefix="/prov")
    app.include_router(audit_router)

    return app


app = create_app()
