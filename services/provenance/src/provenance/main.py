"""ds-provenance — FastAPI application factory."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from .config import get_settings
from .db.engine import verify_schema
from .dependencies import require_read_or_write_scope, require_read_scope, require_write_scope
from .metrics import install_metrics
from .schemas.context import PROV_CONTEXT
from .api.v1.nodes import router as nodes_router
from .api.v1.relations import router as relations_router
from .api.v1.events import router as events_router
from .api.v1.lineage import router as lineage_router
from .api.v1.audit import router as audit_router
from ds_auth.production import ProductionGuard

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await verify_schema()

    settings = get_settings()

    guard = ProductionGuard("ds-provenance")
    guard.require_set(
        "PROVENANCE_OIDC_ISSUER_URL",
        settings.oidc_issuer_url,
        "Point at the Keycloak realm issuer so JWT signatures are verified.",
    )
    guard.forbid_true(
        "PROVENANCE_OIDC_INSECURE_DEV",
        settings.oidc_insecure_dev,
        "Set PROVENANCE_OIDC_INSECURE_DEV=false and configure the issuer URL.",
    )
    guard.enforce()

    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ds-provenance",
        description="W3C PROV-O compatible provenance service",
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
