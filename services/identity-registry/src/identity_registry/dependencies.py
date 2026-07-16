from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth.fastapi import require_permission
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db.engine import get_session_factory

log = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


def get_settings_dep() -> Settings:
    return get_settings()


# ── Authorization guards ────────────────────────────────────────────────────
#
# One unified guard (ds_auth.require_permission) authorizes BOTH service tokens
# (via the `scope` claim) and user tokens (via Keycloak groups). ``{service}.admin``
# is a superset, so an admin service token or an admin-group user both satisfy the
# finer permissions below.

require_admin_scope = require_permission("identity-registry.admin")
require_read_scope = require_permission("identity-registry.read")
require_resolve_scope = require_permission("identity-registry.resolve")
require_admin_or_read_scope = require_permission(
    "identity-registry.admin", "identity-registry.read"
)
