"""FastAPI dependency providers for ds-connector."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth.fastapi import require_exact_permission, require_permission
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


def get_edc(request: Request):
    """Return whichever EDC client is configured (provider or consumer)."""
    return request.app.state.provider_edc or request.app.state.consumer_edc


def get_consumer_service(request: Request):
    return request.app.state.consumer_service


def get_participant_registry(request: Request):
    return request.app.state.registry


def get_notifier(request: Request):
    return request.app.state.notifier


def get_prov(request: Request):
    """The provenance bridge, or None if provenance is not wired."""
    return getattr(request.app.state, "prov", None)


# ── Authorization guards ────────────────────────────────────────────────────
#
# One unified guard (ds_auth.require_permission) authorizes BOTH service tokens
# (via the `scope` claim) and user tokens (via Keycloak groups). ``{service}.admin``
# is a superset, so an admin service token or an admin-group user both satisfy the
# finer provider permissions below.

require_admin = require_permission("connector.admin")
require_provider_read = require_permission("connector.provider.read", "connector.admin")
require_provider_write = require_permission("connector.provider.write", "connector.admin")
require_history_read = require_permission("connector.history.read", "connector.admin")
# Machine identity, not administrative authority — so the admin superset must
# not reach them (require_exact_permission). `connector.webhook` means "I am the
# EDC reporting its own state"; an operator with connector.admin holding it too
# would be able to forge a transfer-process callback. `connector.internal` means
# "I am the dataset-api or an EDC extension", and it opens /internal/edr-jwks —
# the keys that sign data-plane tokens. Neither is something an administrator
# should acquire by being an administrator.
require_internal = require_exact_permission("connector.internal")
require_webhook = require_exact_permission("connector.webhook")
# Onboarding provisions standing consent on a subject's behalf after approval.
# It authenticates as a service (svc-ds-onboarding), not as the subject, so it
# needs its own permission rather than the VC-JWT the /consent/my/* routes use.
require_consent_provision = require_permission(
    "connector.consent.provision", "connector.admin"
)
# "Is this negotiation waiting on a consent decision, and since when" — the
# counterparty's own status question (§6.6). Separate from every other consent
# permission because it is the *only* one a party outside this participant is
# meant to hold, and what it grants is a boolean and a timestamp keyed by an
# unguessable correlation id — never a subject, a count, or a decision.
require_consent_read = require_permission(
    "connector.consent.read", "connector.admin"
)
# An operator records a DSO/offline data handover as they perform it (the DSO
# leg is manual in phase A), so the ingestion event has a human trigger rather
# than an automatic one. connector.admin is a superset.
require_ingestion_record = require_permission(
    "connector.ingestion.record", "connector.admin"
)


# Back-compat aliases (unchanged call sites in admin/internal/consent/webhooks).
#
# `/internal/*` used to also accept `X-Api-Key` equal to `EDC_API_KEY`, because
# the EDC extensions had no other credential. That branch is gone, and with it a
# single static secret that spanned two trust boundaries: the same value was
# EDC's **Management API key** — create/delete assets and policies, terminate
# transfers — *and* the credential for `/internal/edr-jwks`, the keys that sign
# data-plane tokens, and `/internal/consent/check`, which enumerates subject
# pools. One leak yielded all three. It also defeated attribution: every
# `/internal/*` call arrived as the same anonymous bearer, so no audit trail
# could distinguish the EDC from the dataset-api.
#
# Both callers now present their own Keycloak client credentials —
# `svc-edc` and `svc-ds-dataset-api`, each holding `connector.internal`. The
# fallback is removed rather than merely deprecated so it cannot silently
# persist; `EDC_API_KEY` survives only as EDC's Management API key.
require_admin_scope = require_admin
require_internal_scope = require_internal
require_webhook_scope = require_webhook
