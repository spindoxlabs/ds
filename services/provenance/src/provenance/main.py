"""ds-provenance — FastAPI application factory."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from .config import get_settings
from .db.engine import verify_schema
from .dependencies import require_read_or_write_scope, require_write_scope
from .schemas.context import PROV_CONTEXT
from .api.v1.nodes import router as nodes_router
from .api.v1.relations import router as relations_router
from .api.v1.events import router as events_router
from .api.v1.events import subject_router as subject_events_router
from .api.v1.lineage import router as lineage_router
from .api.v1.audit import router as audit_router
from ds_auth.production import ProductionGuard
from ds_obs import configure_logging, install_metrics, install_tracing

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
    # The JWKS every signature is checked against is fetched from this URL.
    # Over plain HTTP an on-path attacker substitutes the key set and every
    # token verifies. `require_https` existed on the guard from the start and
    # was registered by nobody (`AUTH-06`) — a check that is written, tested
    # and never runs, which is the failure this ledger keeps re-finding.
    guard.require_https(
        "PROVENANCE_OIDC_ISSUER_URL",
        settings.oidc_issuer_url,
        "Use an https:// issuer URL; the realm's JWKS is fetched from it.",
    )
    guard.forbid_true(
        "PROVENANCE_OIDC_INSECURE_DEV",
        settings.oidc_insecure_dev,
        "Set PROVENANCE_OIDC_INSECURE_DEV=false and configure the issuer URL.",
    )
    # GET /prov/my/events authenticates a data subject from a verifiable
    # credential. Unverified, anyone could read anyone's history — so the same
    # two settings the connector guards apply here for the same reason.
    guard.require_set(
        "PROVENANCE_TRUST_ANCHOR_DID",
        settings.trust_anchor_did,
        "Name the dataspace's trust anchor; a data subject's credential is "
        "verified against the key that DID's document publishes (`DID-17`).",
    )
    guard.require_set(
        "PROVENANCE_TRUST_LIST_URL",
        settings.trust_list_url,
        "Point at the dataspace trust list so a withdrawn accreditation is "
        "seen before a subject's history is served (DSSC-TRF-05).",
    )
    guard.forbid_true(
        "PROVENANCE_DID_WEB_USE_HTTPS is false",
        not settings.did_web_use_https,
        "Set PROVENANCE_DID_WEB_USE_HTTPS=true.",
    )
    guard.forbid_true(
        "PROVENANCE_VC_INSECURE_DEV",
        settings.vc_insecure_dev,
        "Set PROVENANCE_VC_INSECURE_DEV=false so signatures are verified.",
    )
    guard.enforce()

    yield


def create_app() -> FastAPI:
    settings = get_settings()

    # First, before anything in this process logs. Unconfigured, the root
    # logger drops INFO, so every `log.info` in this service reached nobody
    # and only failures were visible.
    configure_logging("ds-provenance")

    app = FastAPI(
        title="ds-provenance",
        description="W3C PROV-O compatible provenance service",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Auth config is static and must be available even without lifespan (tests).
    from ds_auth import OidcConfig, parse_group_aliases

    app.state.oidc_config = OidcConfig(
        issuer_url=settings.oidc_issuer_url,
        audience=settings.service_client_id,
        insecure_dev=settings.oidc_insecure_dev,
        group_aliases=parse_group_aliases(settings.oidc_group_aliases),
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    install_metrics(app, "ds-provenance")
    # Spans for this service, and outbound spans for every httpx call it
    # makes, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set — the same variable
    # the EDC's Java agent reads, so one value covers both. A no-op
    # otherwise, and it says so once at startup.
    install_tracing(app, "ds-provenance")

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
    # No scope dependency: a data subject reading their own history authenticates
    # with a verifiable credential, verified inside the route. See
    # `services/subject.py` for why the two models stay on separate routers.
    app.include_router(subject_events_router, prefix="/prov")
    # Read **or** write, as the nodes and events routers already do. Requiring
    # `provenance.read` alone locked out the only service that would call it:
    # `svc-ds-connector` holds `provenance.write` and nothing else here, so every
    # lineage read 403'd (rulebook `L-13`). A caller trusted to write the graph is
    # not a narrower principal than one trusted to read it.
    app.include_router(
        lineage_router,
        prefix="/prov",
        dependencies=[Depends(require_read_or_write_scope)],
    )
    app.include_router(
        audit_router,
        dependencies=[Depends(require_read_or_write_scope)],
    )

    return app


app = create_app()
