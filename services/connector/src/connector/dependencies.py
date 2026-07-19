"""FastAPI dependency providers for ds-connector."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth.fastapi import require_permission
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Request

from .config import Settings, get_settings
from .db.engine import get_session_factory

log = logging.getLogger(__name__)


def get_settings_dep() -> Settings:
    return get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


def get_provider_edc(request: Request):
    return request.app.state.provider_edc


def get_consumer_edc(request: Request):
    return request.app.state.consumer_edc


def get_consumer_service(request: Request):
    return request.app.state.consumer_service


def get_participant_registry(request: Request):
    return request.app.state.registry


def get_notifier(request: Request):
    return request.app.state.notifier


# ── Authorization guards ────────────────────────────────────────────────────
#
# One unified guard (ds_auth.require_permission) authorizes BOTH service tokens
# (via the `scope` claim) and user tokens (via Keycloak groups). ``{service}.admin``
# is a superset, so an admin service token or an admin-group user both satisfy the
# finer provider permissions below.

require_admin = require_permission("connector.admin")
require_provider_read = require_permission("connector.provider.read", "connector.admin")
require_provider_write = require_permission("connector.provider.write", "connector.admin")
require_internal = require_permission("connector.internal")
require_webhook = require_permission("connector.webhook")


async def _require_internal_or_api_key(request: Request) -> dict:
    """Accept JWT with connector.internal scope OR X-Api-Key matching EDC_API_KEY.

    The EDC extensions call internal endpoints with X-Api-Key (no JWT available
    in the Java runtime). Falls back to standard JWT auth.
    """
    api_key = request.headers.get("X-Api-Key")
    settings = get_settings()
    if api_key and settings.edc_api_key and api_key == settings.edc_api_key:
        return {"sub": "edc-extension", "scope": "connector.internal"}
    from ds_auth.fastapi import get_oidc_config, authenticate
    from ds_auth import OidcConfig
    from fastapi import HTTPException
    config: OidcConfig = request.app.state.oidc_config
    principal = await authenticate(request, config)
    if not principal.grants_any(("connector.internal",)):
        raise HTTPException(403, "Missing required permission: connector.internal")
    return {"sub": principal.subject, "scope": "connector.internal"}


# Back-compat aliases (unchanged call sites in admin/internal/consent/webhooks).
require_admin_scope = require_admin
require_internal_scope = _require_internal_or_api_key
require_webhook_scope = require_webhook
