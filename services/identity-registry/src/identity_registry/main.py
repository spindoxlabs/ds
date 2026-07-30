from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from ds_auth.production import ProductionGuard
from fastapi import FastAPI

from .api.v1.admin import router as admin_router
from .api.v1.agreements import router as agreements_router
from .api.v1.credentials import router as credentials_router
from .api.v1.memberships import router as memberships_router
from .api.v1.organizations import router as organizations_router
from .api.v1.owners import router as owners_router
from .api.v1.public import router as public_router
from .api.v1.sts import router as sts_router
from .api.v1.users import router as users_router
from .api.v1.onboarding import admin_router as onboarding_admin_router
from .api.v1.onboarding import public_router as onboarding_public_router
from .config import get_settings
from .db.engine import verify_schema

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await verify_schema()

    settings = get_settings()

    guard = ProductionGuard("identity-registry")
    guard.require_set(
        "IDENTITY_REGISTRY_OIDC_ISSUER_URL",
        settings.oidc_issuer_url,
        "Point at the Keycloak realm issuer so JWT signatures are verified.",
    )
    guard.forbid_true(
        "IDENTITY_REGISTRY_OIDC_INSECURE_DEV",
        settings.oidc_insecure_dev,
        "Set IDENTITY_REGISTRY_OIDC_INSECURE_DEV=false and configure the issuer URL.",
    )
    guard.forbid_default(
        "IDENTITY_REGISTRY_ENCRYPTION_KEY",
        settings.encryption_key,
        {"dev-encryption-key-change-in-production"},
        "Generate with: python -c 'import secrets;print(secrets.token_urlsafe(32))'. "
        "Losing this key means losing every stored DID private key.",
    )
    guard.forbid_default(
        "KEYCLOAK_CLIENT_SECRET",
        settings.keycloak_client_secret,
        {"insecure-dev-secret"},
        "Set the Keycloak client secret for the identity-registry admin client.",
    )
    # `KEYCLOAK_MUTATE=true` means this service holds realm-admin rights and
    # creates clients with them when a participant is promoted. That is correct
    # where ds owns the realm and wrong where it is a guest — but either way,
    # holding those rights behind a dev password is the footgun. An *empty*
    # password is not flagged: the promotion path also requires a username, so it
    # is inert, and flagging it would fire on every deployment that simply never
    # needed the feature.
    if settings.keycloak_mutate and settings.keycloak_admin_password:
        guard.forbid_default(
            "KEYCLOAK_ADMIN_PASSWORD",
            settings.keycloak_admin_password,
            {"admin", "changeme", "change-me", "password"},
            "This service can create clients in the realm. Set a real admin "
            "password, or KEYCLOAK_MUTATE=false where ds does not own the realm "
            "(see helm/values.yaml: 'KC is not ours to mutate').",
        )
    guard.enforce()

    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ds-identity-registry",
        description="DID lifecycle, VC issuance, participant registry, StatusList2021",
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

    app.include_router(public_router)
    app.include_router(sts_router)
    app.include_router(credentials_router)
    app.include_router(admin_router)
    app.include_router(memberships_router)
    app.include_router(organizations_router)
    app.include_router(agreements_router)
    app.include_router(owners_router)
    app.include_router(users_router)
    app.include_router(onboarding_admin_router)
    # Applicant-facing intake: no scope guard by design — an organisation
    # applying to join has no identity yet. The invite code in the body is the
    # gate. See api/v1/onboarding.py.
    app.include_router(onboarding_public_router)

    return app


app = create_app()
