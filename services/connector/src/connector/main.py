"""ds-connector — FastAPI application factory."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

log = logging.getLogger(__name__)

from .clients.edc_management import EdcManagementClient
from .clients.provenance import ProvenanceClient
from .config import get_settings
from .db.engine import init_db
from .metrics import install_metrics
from .notifications.factory import build_notifier
from .registry.participants import HttpParticipantRegistry, ParticipantRegistry
from .services.consumer_service import ConsumerService
from .services.prov_bridge import ProvBridge
from .api.v1.provider import router as provider_router
from .api.v1.consumer import router as consumer_router
from .api.v1.webhooks import router as webhooks_router
from .api.v1.internal import router as internal_router
from .api.v1.namespace import router as namespace_router
from .api.v1.consent import router as consent_router
from .api.v1.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()

    if not settings.oidc_issuer_url:
        log.warning(
            "CONNECTOR_OIDC_ISSUER_URL is not set — "
            "JWT signature verification is DISABLED. "
            "This is acceptable for local development only."
        )
    else:
        import jwt as pyjwt

        jwks_url = f"{settings.oidc_issuer_url}/.well-known/openid-configuration"
        app.state.jwks_client = pyjwt.PyJWKClient(jwks_url)

    if settings.edc_api_key == "insecure-dev-key":
        log.warning(
            "EDC_API_KEY is set to the default dev value — "
            "set a strong key for production."
        )

    provider_edc = None
    consumer_edc = None
    consumer_svc = None

    if settings.role == "producer":
        provider_edc = EdcManagementClient(
            base_url=settings.edc_provider_management_url,
            api_key=settings.edc_api_key,
        )

    if settings.role == "consumer":
        consumer_edc = EdcManagementClient(
            base_url=settings.edc_consumer_management_url,
            api_key=settings.edc_api_key,
        )

    # Participant registry
    http_registry = None
    if settings.identity_registry_url:
        http_registry = HttpParticipantRegistry(
            settings.identity_registry_url,
            cache_ttl=settings.participant_registry_cache_ttl,
        )
        registry = http_registry
    elif settings.participants_registry_path:
        registry = ParticipantRegistry.from_file(
            Path(settings.participants_registry_path)
        )
    else:
        registry = ParticipantRegistry.empty()

    # Provenance bridge
    prov_client = ProvenanceClient(settings.provenance_url)
    prov = ProvBridge(prov_client, settings.participant_id)

    if consumer_edc is not None:
        consumer_svc = ConsumerService(
            consumer_edc=consumer_edc,
            registry=registry,
            prov=prov,
            poll_interval=settings.negotiation_poll_interval,
            negotiation_timeout=settings.negotiation_timeout,
            transfer_timeout=settings.transfer_timeout,
            participant_id=settings.participant_id,
            provider_id=settings.participant_did,
            allow_unknown_participants=settings.allow_unknown_participants,
        )

    # Notifier
    notifier = build_notifier(settings)

    app.state.provider_edc = provider_edc
    app.state.consumer_edc = consumer_edc
    app.state.consumer_service = consumer_svc
    app.state.registry = registry
    app.state.prov = prov
    app.state.notifier = notifier

    yield

    if http_registry is not None:
        await http_registry.close()
    if provider_edc is not None:
        await provider_edc.close()
    if consumer_edc is not None:
        await consumer_edc.close()
    await prov_client.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ds-connector",
        description="EDC control plane management for the dataspaces platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "role": settings.role, "version": "0.1.0"}

    install_metrics(app, "ds-connector")

    # Shared routers — always mounted
    app.include_router(webhooks_router)
    app.include_router(internal_router)
    app.include_router(namespace_router)
    app.include_router(consent_router)
    app.include_router(admin_router)

    # Role-specific routers
    if settings.role == "producer":
        app.include_router(provider_router)

    if settings.role == "consumer":
        app.include_router(consumer_router)

    return app


app = create_app()
