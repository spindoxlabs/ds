"""ds-connector — FastAPI application factory."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

log = logging.getLogger(__name__)

from .clients.edc_management import EdcManagementClient
from .clients.provenance import ProvenanceClient
from .config import get_settings
from .db.engine import verify_schema
from .metrics import install_metrics
from .notifications.factory import build_notifier
from ds.governance.owners import HttpOwnersRegistry
from ds_auth.production import ProductionGuard
from ds_auth.service_token import ServiceTokenProvider
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
from .api.v1.history import router as history_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await verify_schema()

    guard = ProductionGuard("ds-connector")
    guard.require_set(
        "CONNECTOR_OIDC_ISSUER_URL",
        settings.oidc_issuer_url,
        "Point at the Keycloak realm issuer so JWT signatures are verified.",
    )
    guard.forbid_true(
        "CONNECTOR_OIDC_INSECURE_DEV",
        settings.oidc_insecure_dev,
        "Set CONNECTOR_OIDC_INSECURE_DEV=false and configure the issuer URL.",
    )
    guard.require_set(
        "CONNECTOR_TRUST_ANCHOR_KEY_PATH",
        settings.trust_anchor_key_path,
        "Mount the trust-anchor public key so user Verifiable Credentials "
        "are signature-verified.",
    )
    guard.forbid_true(
        "CONNECTOR_VC_INSECURE_DEV",
        settings.vc_insecure_dev,
        "Set CONNECTOR_VC_INSECURE_DEV=false once the trust-anchor key is mounted.",
    )
    guard.forbid_default(
        "EDC_API_KEY",
        settings.edc_api_key,
        {"insecure-dev-key"},
        "Generate with: openssl rand -hex 32",
    )
    guard.forbid_default(
        "CONNECTOR_SERVICE_CLIENT_SECRET",
        settings.service_client_secret,
        {"svc-ds-connector"},
        "Set the Keycloak client secret for svc-ds-connector.",
    )
    guard.enforce()

    provider_edc = None
    consumer_edc = None
    consumer_svc = None

    if settings.role == "provider":
        provider_edc = EdcManagementClient(
            base_url=settings.edc_provider_management_url,
            api_key=settings.edc_api_key,
        )

    if settings.role == "consumer":
        consumer_edc = EdcManagementClient(
            base_url=settings.edc_consumer_management_url,
            api_key=settings.edc_api_key,
        )

    # Service token for identity-registry calls
    ir_token_provider = ServiceTokenProvider(
        token_url=settings.keycloak_token_url,
        client_id=settings.service_client_id,
        client_secret=settings.service_client_secret,
    )

    # Participant registry
    http_registry = None
    if settings.identity_registry_url:
        http_registry = HttpParticipantRegistry(
            settings.identity_registry_url,
            cache_ttl=settings.participant_registry_cache_ttl,
            token_provider=ir_token_provider,
        )
        registry = http_registry
    elif settings.participants_registry_path:
        registry = ParticipantRegistry.from_file(
            Path(settings.participants_registry_path)
        )
    else:
        registry = ParticipantRegistry.empty()

    # Provenance bridge
    prov_client = ProvenanceClient(settings.provenance_url, token_provider=ir_token_provider)
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

    # Owners registry
    owners_registry = None
    if settings.identity_registry_url:
        owners_registry = HttpOwnersRegistry(
            settings.identity_registry_url,
            cache_ttl=settings.owners_registry_cache_ttl,
            token_provider=ir_token_provider,
        )

    # Notifier
    notifier = build_notifier(settings)

    app.state.provider_edc = provider_edc
    app.state.consumer_edc = consumer_edc
    app.state.consumer_service = consumer_svc
    app.state.registry = registry
    app.state.owners_registry = owners_registry
    app.state.prov = prov
    app.state.notifier = notifier
    app.state.ir_token_provider = ir_token_provider

    yield

    if owners_registry is not None:
        await owners_registry.close()
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

    # Auth config is static and must be available even without lifespan (tests).
    from ds_auth import OidcConfig

    app.state.oidc_config = OidcConfig(
        issuer_url=settings.oidc_issuer_url,
        audience=settings.service_client_id,
        insecure_dev=settings.oidc_insecure_dev,
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
    app.include_router(history_router)

    # Role-specific routers
    if settings.role == "provider":
        app.include_router(provider_router)

    if settings.role == "consumer":
        app.include_router(consumer_router)

    return app


app = create_app()
