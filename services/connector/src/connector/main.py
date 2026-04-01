"""ds-connector — FastAPI application factory."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .clients.edc_management import EdcManagementClient
from .clients.provenance import ProvenanceClient
from .config import get_settings
from .db.engine import init_db
from .notifications.factory import build_notifier
from .registry.participants import ParticipantRegistry
from .services.consumer_service import ConsumerService
from .services.prov_bridge import ProvBridge
from .api.v1.provider import router as provider_router
from .api.v1.consumer import router as consumer_router
from .api.v1.webhooks import router as webhooks_router
from .api.v1.internal import router as internal_router
from .api.v1.namespace import router as namespace_router
from .api.v1.consent import router as consent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()

    # EDC clients
    provider_edc = EdcManagementClient(
        base_url=settings.edc_provider_management_url,
        api_key=settings.edc_api_key,
    )
    consumer_edc = EdcManagementClient(
        base_url=settings.edc_consumer_management_url,
        api_key=settings.edc_api_key,
    )

    # Participant registry
    registry = ParticipantRegistry.from_file(
        Path(settings.participants_registry_path)
    )

    # Provenance bridge
    prov_client = ProvenanceClient(settings.provenance_url)
    prov = ProvBridge(prov_client, settings.participant_id)

    # Consumer service
    consumer_svc = ConsumerService(
        consumer_edc=consumer_edc,
        registry=registry,
        prov=prov,
        poll_interval=settings.negotiation_poll_interval,
        negotiation_timeout=settings.negotiation_timeout,
        transfer_timeout=settings.transfer_timeout,
        participant_id=settings.participant_id,
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

    await provider_edc.close()
    await consumer_edc.close()
    await prov_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ds-connector",
        description="EDC control plane management for the dataspaces platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(provider_router)
    app.include_router(consumer_router)
    app.include_router(webhooks_router)
    app.include_router(internal_router)
    app.include_router(namespace_router)
    app.include_router(consent_router)

    return app


app = create_app()
