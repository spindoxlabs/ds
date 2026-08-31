"""FastAPI dependency providers for ds-connector."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache

import httpx
from ds_auth import Principal
from ds_auth.errors import PermissionDenied
from ds_auth.fastapi import require_exact_permission, require_permission
from ds_auth.user_credentials import verify_user_vc_jwt
from fastapi import Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

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

# There is deliberately no bare `require_admin` guard. `connector.admin` enters
# only as the second argument below, as the superset that satisfies a finer
# permission — never as a requirement of its own. A route that demanded admin and
# nothing weaker would be a route no service client can call, since `clients.yaml`
# forbids `*.admin` on one; the guard existed, was declared by no route, and its
# presence invited exactly that.
require_provider_read = require_permission("connector.provider.read", "connector.admin")
require_provider_write = require_permission(
    "connector.provider.write", "connector.admin"
)


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


@lru_cache(maxsize=1)
def _owner_aliases(raw: str) -> dict[str, str]:
    """Parse the Layer B owner map: a foreign organisation alias → ds ``Owner.id``.

    Cached on the raw string because it is read per request and the value is
    process-lifetime configuration. Malformed JSON yields an empty map and a logged
    error rather than a partial one — a typo must not silently become a *different*
    mapping, and empty means "the realm already uses ds owner ids", which is the
    pre-existing behaviour.
    """
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        log.error(
            "CONNECTOR_OWNER_ALIASES is not valid JSON (%s) — no owner aliases "
            'applied. Expected {"foreign-org": "ds-owner-id"}.',
            exc,
        )
        return {}
    if not isinstance(parsed, dict):
        log.error("CONNECTOR_OWNER_ALIASES must be a JSON object — ignoring.")
        return {}
    aliases = {
        k: v for k, v in parsed.items() if isinstance(k, str) and isinstance(v, str)
    }
    if aliases:
        log.info(
            "owner alias map active — %s",
            ", ".join(f"{k} -> {v}" for k, v in sorted(aliases.items())),
        )
    return aliases


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
    # Layer B first: translate a *foreign* organisation name into a ds owner id,
    # then let the registry resolve ds's own aliases. Doing it the other way round
    # would ask the registry about a name it has never heard of.
    alias = _owner_aliases(get_settings().owner_aliases).get(alias, alias)

    registry = getattr(request.app.state, "owners_registry", None)
    if registry is None:
        return alias
    try:
        entry = await registry.by_id(alias)
    except Exception:  # noqa: BLE001 — a registry blip must not decide authority
        return alias
    return entry.id if entry is not None else alias


class OwnerUnknown(Exception):
    """The owner of the target could not be determined.

    Deliberately distinct from *the target has no owner*: one is an answer this
    perimeter can act on, the other is the absence of one. Collapsing them is
    `ENV-09`, and it opened the perimeter for as long as the lookup was failing.
    """


async def _target_owner(request: Request) -> str:
    """The owning organisation of whatever this request is about to mutate.

    Two different lookups, because EDC labels only one of the three object kinds:

    * **assets** carry `ds:owner` (well, ``f"{profile_prefix}:owner"`` — see
      :func:`_asset_owner`), so the object answers for itself.
    * **policy and contract definitions** carry nothing. Their ids are *derived
      from the dataset key*, so governance is the only thing that knows which
      owner they belong to. Asking EDC cannot work: a contract definition
      references assets only through a selector and a policy definition
      references nothing at all.

    Returns ``""`` when there is genuinely no owner to scope against — an unowned
    dataset, or an id governance does not know. Neither is an authorization
    decision: a missing object is the endpoint's 404 to report, and refusing
    there would turn "does not exist" into "not yours", which is a worse answer
    and a weaker one.

    Raises :class:`OwnerUnknown` when the lookup **failed** — which used to
    return ``""`` as well, and that was a fail-open (`ENV-09`). *There is no
    owner* and *I could not find out who the owner is* are different states, and
    only the first is safe to allow: with the provider EDC unreachable, an
    operator for one participant passed this perimeter on another participant's
    asset. Same rule the Java constraint functions are held to in the root
    guide — a guard denies on error — and the same two-absent-states rule as
    `CI-02`.

    The split is by *what EDC said*: a 404 is an answer (there is no such asset,
    so there is no owner), anything else is the absence of one.
    """
    asset_id = request.path_params.get("asset_id")
    if asset_id:
        edc = getattr(request.app.state, "provider_edc", None)
        if edc is None:
            raise OwnerUnknown("the provider EDC client is not configured")
        try:
            asset = await edc.get_asset(asset_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return ""
            raise OwnerUnknown(
                f"EDC answered {exc.response.status_code} for asset {asset_id!r}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 — transport, timeout, anything
            raise OwnerUnknown(
                f"the provider EDC could not be reached for asset {asset_id!r}: {exc}"
            ) from exc
        return _asset_owner((asset or {}).get("properties") or {})

    object_id = request.path_params.get("policy_id") or request.path_params.get(
        "contract_id"
    )
    if not object_id:
        return ""

    settings = get_settings()
    try:
        from .services.governance import owner_by_edc_id

        index = owner_by_edc_id(
            settings.governance_yaml_path,
            overlay_name=settings.governance_overlay_name,
        )
    except Exception as exc:  # noqa: BLE001
        # Governance is a file this process may fail to read. This comment used
        # to end "say so rather than deciding authority from an empty index,
        # which would silently unscope every policy and contract" — and then
        # returned "", which is exactly that. Saying so is the log line; the
        # decision is the raise.
        log.error(
            "owner scoping: could not read governance to resolve %r (%s)",
            object_id,
            exc,
        )
        raise OwnerUnknown(f"governance could not be read: {exc}") from exc
    return index.get(object_id, "")


def _models_no_organisations(principal: Principal) -> bool:
    """Whether owner scoping can decide anything at all for this caller.

    A caller with no organisation claims in a deployment that has not turned
    `owner_scoping_strict` on is allowed either way, so a failed owner lookup
    changes nothing for them — refusing there would trade an availability
    regression for no security gain. Named once because the `ENV-09` refusal and
    the ordinary path both have to ask it, and two copies of this condition
    would drift into disagreeing about who is exempt.
    """
    return not principal.organizations and not get_settings().owner_scoping_strict


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
    * a target with **no owner** — ownership is optional in ``governance.yaml`` and
      an unowned dataset belongs to the participant as a whole. Mirrors the portal.
      Assets are labelled by EDC; policies and contracts are resolved through
      governance, because EDC labels neither (:func:`_target_owner`).
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

    try:
        owner = await _target_owner(request)
    except OwnerUnknown as exc:
        # The lookup failed, so this perimeter has nothing to decide with — and
        # the safe direction is a refusal (`ENV-09`). Two things bound the cost
        # of that, and both are above: `connector.admin` and every service
        # principal have already returned, so an EDC outage cannot break the
        # governance sync or lock the deployment operator out of the fix.
        if _models_no_organisations(principal):
            log.warning(
                "owner scoping: could not determine the owner for caller %s (%s); "
                "allowing, because this caller holds no organisation claims and "
                "CONNECTOR_OWNER_SCOPING_STRICT is off — owner scoping cannot "
                "decide anything for them either way.",
                principal.subject,
                exc,
            )
            return True
        log.error(
            "owner scoping: refusing a provider write for caller %s — the owner "
            "of the target could not be determined (%s)",
            principal.subject,
            exc,
        )
        # `PermissionDenied` rather than a bare False: `require_permission`
        # turns it into a 403 carrying this message, so the refusal says *why*.
        # An unattributable 403 during an EDC outage is the kind of alarm that
        # gets dismissed, and this one is worth acting on.
        raise PermissionDenied(
            f"cannot determine which organisation owns this object ({exc}) — "
            "refusing rather than allowing a write that may cross an owner "
            "boundary"
        ) from exc

    if not owner:
        return True

    if _models_no_organisations(principal):
        log.info(
            "owner scoping: caller %s holds no organisation claims; allowing "
            "write to owner %r. Set CONNECTOR_OWNER_SCOPING_STRICT=true where "
            "organisations are modelled.",
            principal.subject,
            owner,
        )
        return True
    if not principal.organizations:
        return False

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
require_consent_read = require_permission("connector.consent.read", "connector.admin")
# "Who consents to this offer" — the cross-subject read, and the counterpart to
# `connector.consent.provision` beside it: onboarding can write a standing
# consent and needs to read one back before it exports against it.
#
# **A separate permission, and not a reuse of `.provision`.** Reuse costs nothing
# in either realm, which is why it was considered; it was rejected because
# `.provision` is in the `ds-participant-admin` bundle, so every participant
# operator would acquire bulk subject enumeration as a side effect of holding a
# *write* grant. `GET /consent/status` already refuses that capability to an
# authenticated subject — "without this check any authenticated holder could
# enumerate another subject's consent decisions" — and granting it wholesale by
# accident is worse than granting it on purpose.
#
# `require_permission`, not `require_exact_permission`: this is administrative
# authority over this participant's own consent records, not a machine identity,
# so `connector.admin` is a superset exactly as it is for `.provision`.
#
# **Not to be merged with `connector.internal`.** `GET /internal/consent/check`
# answers a nearly identical question and stays where it is: it is the machine
# identity for the data plane and the EDC, exempt from the admin superset,
# dataset-keyed, and it fails closed to an empty list when the caller declares no
# purpose. This one is offer-keyed on the published plane and reachable by a
# `ds-admin` human. Merging them would put the internal surface behind an
# admin-reachable grant.
require_consent_audience = require_permission(
    "connector.consent.audience", "connector.admin"
)
# An operator records a DSO/offline data handover as they perform it (the DSO
# leg is manual in phase A), so the ingestion event has a human trigger rather
# than an automatic one. connector.admin is a superset.
require_ingestion_record = require_permission(
    "connector.ingestion.record", "connector.admin"
)
# The outbound counterpart: data leaving the platform to a named recipient.
# **A separate permission from `ingestion.record`, not a reuse of it.** The two
# are opposite directions across the same boundary, and the out-of-repo service
# that discloses after a CSV export has no business recording inbound handovers
# — nor the reverse. Granting one to get the other is how a scope stops meaning
# anything.
require_disclosure_record = require_permission(
    "connector.disclosure.record", "connector.admin"
)


# `/consumer/catalog` — a service driving the consumer side. A *person* browsing
# a counterparty's catalogue authenticates with a `ConsumerUser` VC-JWT instead;
# see `require_consumer_catalog_caller`, which accepts either.
require_consumer_read = require_permission("connector.consumer.read", "connector.admin")


@dataclass(frozen=True)
class CatalogCaller:
    """Who asked for a counterparty's catalogue, having proved it.

    ``subject_id`` is the DID of a natural person when one presented a
    ``ConsumerUser`` credential, and ``None`` when a service authenticated on a
    scope. ``actor`` is whichever of the two is present, and is what provenance
    attributes the ``CatalogViewed`` event to.
    """

    subject_id: str | None
    actor: str
    is_service: bool


async def require_consumer_catalog_caller(
    request: Request,
    x_subject_id: str | None = Header(default=None),
    x_user_vc: str | None = Header(default=None),
) -> CatalogCaller:
    """Authenticate a catalogue request by **either** mechanism, never neither.

    This route has two legitimate caller classes and they authenticate
    differently, which is why it gets its own dependency rather than one of the
    two standard guards:

    * a **person** acting for a consumer organisation, carrying
      ``X-Subject-Id`` + ``X-User-VC`` — the same mechanism every other
      ``/consumer/*`` route uses, and the one `ds-e2e`'s smoke flow presents;
    * a **service** driving the consumer side on the participant's behalf —
      today `ds-federated-catalog`'s crawler — carrying a Keycloak
      client-credentials token with ``connector.consumer.read``.

    The route previously had no guard at all, which is rulebook `C-19`
    (`DSSC-PUB-27`, a discovering consumer must be a registered participant) and
    defect **P0-1**. It also meant `CatalogViewed` was attributed to a
    caller-supplied header — rulebook `D-16`, which requires the recorded
    identity to be a verified one. Both close here: what this returns is the
    *verified* identity, and the route has nothing else to attribute to.

    Presenting a VC takes precedence over presenting a token, so a person whose
    client also happens to hold the service scope is still recorded as that
    person.
    """
    settings = get_settings()
    if x_user_vc or x_subject_id:
        credential = verify_user_vc_jwt(
            x_user_vc,
            x_subject_id,
            settings.trust_anchor_did,
            {"ConsumerUser"},
            trust_list_url=settings.trust_list_url,
            did_web_use_https=settings.did_web_use_https,
            expected_linked_participant=settings.consumer_participant_did,
            credential_status_path=settings.credential_status_path,
            credential_status_url=settings.credential_status_url,
            insecure_dev=settings.vc_insecure_dev,
        )
        return CatalogCaller(
            subject_id=credential.subject_id,
            actor=credential.subject_id,
            is_service=False,
        )

    principal = await require_consumer_read(request, get_oidc_config_for(request))
    return CatalogCaller(subject_id=None, actor=principal.subject, is_service=True)


def get_oidc_config_for(request: Request):
    """The app's OIDC config, for composing a ds_auth guard by hand.

    ``require_permission`` returns a FastAPI dependency whose second parameter is
    normally filled by ``Depends``. Calling it directly — which is what an
    either/or guard has to do — means supplying it here.
    """
    from ds_auth.fastapi import get_oidc_config

    return get_oidc_config(request)


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
require_internal_scope = require_internal
require_webhook_scope = require_webhook
