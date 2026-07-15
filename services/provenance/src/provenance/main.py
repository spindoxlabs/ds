"""ds-provenance — FastAPI application factory."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from .config import get_settings
from .db.engine import init_db
from .dependencies import require_read_or_write_scope, require_read_scope, require_write_scope
from .metrics import install_metrics
from .schemas.context import PROV_CONTEXT
from .api.v1.nodes import router as nodes_router
from .api.v1.relations import router as relations_router
from .api.v1.events import router as events_router
from .api.v1.lineage import router as lineage_router
from .api.v1.audit import router as audit_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    settings = get_settings()
    if not settings.oidc_issuer_url:
        log.warning(
            "PROVENANCE_OIDC_ISSUER_URL is not set — "
            "JWT signature verification is DISABLED. "
            "This is acceptable for local development only."
        )
    else:
        import jwt

        jwks_url = f"{settings.oidc_issuer_url}/.well-known/openid-configuration"
        app.state.jwks_client = jwt.PyJWKClient(jwks_url)

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ds-provenance",
        description="W3C PROV-O compatible provenance service",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    install_metrics(app, "ds-provenance")

    @app.get("/prov/context", response_class=JSONResponse)
    async def context():
        return JSONResponse(
            content={"@context": PROV_CONTEXT},
            media_type="application/ld+json",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    app.include_router(
        nodes_router,
        prefix="/prov",
        dependencies=[Depends(require_read_or_write_scope)],
    )
    app.include_router(
        relations_router,
        prefix="/prov",
        dependencies=[Depends(require_write_scope)],
    )
    app.include_router(
        events_router,
        prefix="/prov",
        dependencies=[Depends(require_read_or_write_scope)],
    )
    app.include_router(
        lineage_router,
        prefix="/prov",
        dependencies=[Depends(require_read_scope)],
    )
    app.include_router(
        audit_router,
        dependencies=[Depends(require_read_or_write_scope)],
    )

    return app


app = create_app()
