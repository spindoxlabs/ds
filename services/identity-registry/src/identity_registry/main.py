from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from ds_auth.production import ProductionGuard
from ds_obs import configure_logging
from fastapi import FastAPI

from .config import get_settings
from .db.engine import verify_schema
from .roles import RoleConfigurationError, audit, normalize_role, specs_for_role

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
    # Resolving a counterparty's DID document over plain HTTP means the key a
    # signature is checked against arrives unauthenticated — anyone on the path
    # substitutes it and speaks as that participant. Dev needs it (Caddy serves
    # did:web on :80), production must never have it, and this is the Python
    # counterpart of the EDC's own `edc.iam.did.web.use.https`.
    if not settings.did_web_use_https:
        guard.add(
            "IDENTITY_REGISTRY_DID_WEB_USE_HTTPS",
            "is false — a counterparty's verification key would be fetched over "
            "plain HTTP",
            "Set IDENTITY_REGISTRY_DID_WEB_USE_HTTPS=true so DID documents are "
            "fetched over TLS.",
        )
    guard.forbid_default(
        "IDENTITY_REGISTRY_ENCRYPTION_KEY",
        settings.encryption_key,
        {"dev-encryption-key-change-in-production"},
        "Generate with: python -c 'import secrets;print(secrets.token_urlsafe(32))'. "
        "Losing this key means losing every stored DID private key.",
    )
    # This service's own outbound credential — the one it actually
    # authenticates with. It ships a dev default equal to the client id and was
    # the only such secret with no guard. (`KEYCLOAK_CLIENT_SECRET` was guarded
    # here instead and authenticated nothing; both it and its setting are gone.)
    guard.forbid_default(
        "IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET",
        settings.service_client_secret,
        {"svc-ds-identity-registry"},
        "Set the Keycloak client secret for svc-ds-identity-registry — this is "
        "the credential the registry presents on its own outbound calls.",
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

    await _warn_on_duplicate_status_list_indices()

    yield


async def _warn_on_duplicate_status_list_indices() -> None:
    """Surface credentials issued with colliding StatusList indices.

    A warning and never a refusal. The collisions are pre-existing damage from
    the allocator this service used before schema 0011, and the index lives
    inside the *signed* credential — so nothing here can repair them, and
    refusing to start would take a working registry offline over credentials
    that are already issued. The fix is re-issuance, which is an operator's
    decision.

    It logs on every start rather than once, because the only action it can
    prompt is one a person has to take, and a single line in a pod's first log
    is a line nobody reads.
    """
    from .db.engine import get_session_factory
    from .services.status_list import find_duplicate_indices

    try:
        async with get_session_factory()() as session:
            duplicates = await find_duplicate_indices(session)
    except Exception:  # noqa: BLE001 — diagnostics must never block startup
        log.exception("could not check StatusList indices for duplicates")
        return

    if not duplicates:
        return

    affected = sum(len(d.credential_ids) for d in duplicates)
    log.warning(
        "%d credentials share %d StatusList %s — revoking one of a group "
        "revokes the whole group. These were issued by a pre-0011 allocator and "
        "cannot be corrected in place (the index is inside the signed "
        "credential); they must be re-issued. Details: ir-cli status "
        "check-indices",
        affected,
        len(duplicates),
        "index" if len(duplicates) == 1 else "indices",
    )
    for d in duplicates:
        log.warning("  %s", d)


def create_app() -> FastAPI:
    settings = get_settings()

    # First, before anything in this process logs. Unconfigured, the root
    # logger drops INFO, so every `log.info` in this service reached nobody
    # and only failures were visible.
    configure_logging("ds-identity-registry")

    # Before the app exists: an unknown role is a refusal, not a fallback to
    # trust-anchor. Silently promoting a typo'd `participant` to the issuing role
    # is precisely the failure this split exists to make impossible.
    role = normalize_role(settings.role)

    app = FastAPI(
        title="ds-identity-registry",
        description="DID lifecycle, VC issuance, participant registry, StatusList2021",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Auth config is static and must be available even without lifespan (tests).
    from ds_auth import OidcConfig, parse_group_aliases

    app.state.oidc_config = OidcConfig(
        issuer_url=settings.oidc_issuer_url,
        audience=settings.service_client_id,
        insecure_dev=settings.oidc_insecure_dev,
        group_aliases=parse_group_aliases(settings.oidc_group_aliases),
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "role": role, "version": "0.1.0"}

    # Mount by role, then check the result against an independent classification
    # of every path. `roles.py` explains why both halves exist; the short version
    # is that this is the one kind of check that fails because of something a
    # change *did not* do — mounting a router nobody classified, or classifying a
    # path nobody mounted.
    #
    # Applicant-facing intake (`/onboarding/applications`) carries no scope guard
    # by design — an organisation applying to join has no identity yet, and the
    # invite code in the body is the gate. It is anchor-only, which is now
    # enforced rather than implied. See api/v1/onboarding.py.
    mounted: list[str] = ["/health"]
    for spec in specs_for_role(role):
        app.include_router(spec.router)
        mounted.extend(spec.paths())

    problems = audit(role, mounted)
    if problems:
        raise RoleConfigurationError(
            f"identity-registry role {role!r} is misconfigured:\n  - "
            + "\n  - ".join(problems)
        )

    log.info(
        "identity-registry starting as %r — %d routers, %d paths",
        role,
        len(specs_for_role(role)),
        len(set(mounted)),
    )

    return app


app = create_app()
