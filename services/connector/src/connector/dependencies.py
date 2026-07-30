"""FastAPI dependency providers for ds-connector."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from ds_auth import Principal
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


def _asset_owner(properties: dict) -> str:
    """The owning organisation's alias, read by **local name**.

    The property is written as ``f"{prefix}:owner"`` where the prefix comes from the
    active ODRL profile (``services/connector/services/governance.py``) — today
    ``dsp-policy``, and a deployment may change it. EDC also returns properties
    JSON-LD-compacted, so the key that comes back is not necessarily the key that
    went in.

    A hardcoded key is therefore wrong in two independent ways, and it fails
    **silently**: an unrecognised key reads as "no owner", which the perimeter
    treats as unowned and allows. That is exactly how the first cut of this guard
    passed its unit tests (against a key those tests invented) while enforcing
    nothing at all against a real EDC. Match on the local name and the prefix stops
    mattering.
    """
    for key, value in (properties or {}).items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        local = key.rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        if local == "owner" and value.strip():
            return value.strip()
    return ""


async def _canonical_owner(request: Request, alias: str) -> str:
    """Resolve an owner alias to its canonical ``Owner.id``.

    An owner answers to more than one name: ``Owner.aliases[]`` means ``example-org``
    is also ``example``. A governance file using the short form and a realm using
    the long one describe the same organisation and compare unequal as strings, so
    both sides go through the registry — which resolves aliases server-side
    (``GET /owners/resolve`` falls back to scanning them) and is already TTL-cached
    in this process.

    Falls back to the alias itself when there is no registry or the owner is
    unknown, so a deployment without one is scoped on literal names rather than
    silently unscoped.
    """
    registry = getattr(request.app.state, "owners_registry", None)
    if registry is None:
        return alias
    try:
        entry = await registry.by_id(alias)
    except Exception:  # noqa: BLE001 — a registry blip must not decide authority
        return alias
    return entry.id if entry is not None else alias


async def _own_owner_only(principal: Principal, request: Request) -> bool:
    """Confine a provider write to the owner the caller holds authority *for*.

    ``connector.provider.write`` says *what* a caller may do; it never said *whose*
    data they may do it to. The portal filtered its buttons by owner, but the API
    accepted the call regardless — so an operator for one participant could delete
    another participant's asset. The bundle ``ds-participant-admin`` is documented
    as scoped to one participant; this is what makes that true.

    **Authority, not membership.** The question asked is
    :meth:`Principal.grants_in` — "does this caller hold ``connector.provider.write``
    *within* this owner" — not "is a member of it". Membership alone was the
    fail-open case: a read-only auditor for owner A who administers owner B was
    reported by flattened authority as an administrator, and A's assets were
    writable.

    Membership and per-organisation authority both come from the Keycloak
    ``organization`` claim, which is the *operator → owner* relation. Deliberately
    **not** the identity-registry's ``OrganizationMembership``: that is the consent
    subject-pool keyed by a data subject's DID, and an operator legitimately has no
    DID at all. The two membership systems stay separate, as documented.

    Four exemptions, each deliberate:

    * ``connector.admin`` — the *deployment operator's* grant, not a participant's.
      It crosses owners by design; that is what distinguishes it from
      ``ds-participant-admin``.
    * **service principals** — they authorise on scopes, hold no organisations, and
      run the syncs. Checked explicitly here so the exemption is visible.
    * an asset with **no owner** — ownership is optional in ``governance.yaml`` and
      an unowned asset belongs to the participant as a whole. Mirrors the portal.
    * a caller with **no organisation claims at all**, unless
      ``owner_scoping_strict``. A deployment that models no organisations is not
      one where every operator has lost their rights; refusing there would push
      operators towards ``connector.admin``, which is strictly worse than the
      thing being prevented. Deployments that *do* model owners can set the flag
      and get the tighter posture.
    """
    if principal.grants("connector.admin"):
        return True
    if principal.is_service:
        return True

    asset_id = request.path_params.get("asset_id")
    if not asset_id:
        # Policies and contracts are not owner-labelled in EDC, so there is
        # nothing to scope against here. Named so the gap is visible rather than
        # implied — scoping them means going through governance, not EDC.
        return True

    edc = getattr(request.app.state, "provider_edc", None)
    if edc is None:
        return True

    try:
        asset = await edc.get_asset(asset_id)
    except Exception:  # noqa: BLE001
        # A missing asset is the endpoint's 404 to report, not an authorization
        # decision. Refusing here would turn "does not exist" into "not yours",
        # which is a worse answer and a weaker one.
        return True

    owner = _asset_owner((asset or {}).get("properties") or {})
    if not owner:
        return True

    if not principal.organizations:
        strict = get_settings().owner_scoping_strict
        if not strict:
            log.info(
                "owner scoping: caller %s holds no organisation claims; allowing "
                "write to owner %r. Set CONNECTOR_OWNER_SCOPING_STRICT=true where "
                "organisations are modelled.",
                principal.subject,
                owner,
            )
        return not strict

    target = await _canonical_owner(request, owner)
    for alias in principal.organization_aliases:
        if await _canonical_owner(request, alias) != target:
            continue
        if principal.grants_in(alias, "connector.provider.write"):
            return True
    return False


# Owner-scoped variant. Used where the target carries an owner; the unscoped
# `require_provider_write` remains for endpoints that act on the participant as a
# whole (e.g. the governance sync, which publishes every owner's datasets at once).
require_provider_write_own = require_permission(
    "connector.provider.write", "connector.admin", perimeter=_own_owner_only
)
require_history_read = require_permission("connector.history.read", "connector.admin")
# Machine identity, not administrative authority — so the admin superset must
# not reach them (require_exact_permission). `connector.webhook` means "I am the
# EDC reporting its own state"; an operator with connector.admin holding it too
# would be able to forge a transfer-process callback. `connector.internal` means
# "I am the dataset-api or an EDC extension", and it opens /internal/edr-jwks —
# the keys that sign data-plane tokens. Neither is something an administrator
# should acquire by being an administrator.
require_internal = require_exact_permission("connector.internal")
# A hint, not an authority: it takes no input and returns a boolean. Held by the
# identity-registry, which knows when the participant list changed.
require_registry_invalidate = require_permission("connector.registry.invalidate")
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
