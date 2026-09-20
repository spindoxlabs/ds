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
# is a superset of the finer permissions below.

# **Two guards, and no third that accepts either.** `require_read_or_write_scope`
# existed until 2026-09-20 and was the mount of every mixed router, which made
# `provenance.write` a read credential for the whole store. Measured live: three
# organisation clients holding `provenance.write` alone read every event in
# another participant's store, a collector's withdrawal `reason` included — the
# one field `ADR-0019` says no read returns.
#
# The assumption it rested on is in the route's own comment: *"Each participant
# runs its own provenance store, so … there is no cross-participant read to guard
# against here."* The store is per participant. The **realm is not**: in a
# one-realm-many-stacks deployment every participant's client is a valid caller at
# every participant's store, and only the scope stands between them.
#
# Router-level dependencies are **and**ed with route-level ones, so a mixed router
# cannot express this: mounting reads under `provenance.read` would demand read
# *and* write of every writer. Each route states its own scope instead, and
# `tests/test_auth.py::test_every_route_declares_exactly_one_scope_and_it_matches_the_verb`
# is what keeps the next route from being added without one.
require_read_scope = require_permission("provenance.read")
require_write_scope = require_permission("provenance.write")
