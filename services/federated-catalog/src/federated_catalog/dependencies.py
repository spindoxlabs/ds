from __future__ import annotations

from ds_auth.fastapi import require_permission

from .config import Settings, get_settings


def get_settings_dep() -> Settings:
    return get_settings()


# ── Authorization guards ────────────────────────────────────────────────────
#
# One unified guard (ds_auth.require_permission) authorizes BOTH service tokens
# (via the `scope` claim) and user tokens (via Keycloak groups). ``{service}.admin``
# is a superset.

require_read_scope = require_permission("catalog.read")
