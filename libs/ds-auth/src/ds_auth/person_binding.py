"""A person route acts for the person who logged in, not for whoever holds their credential.

A user credential (``X-User-VC``) is a **bearer** credential: the person holds no
key and signs nothing (`D-22`, `D-49`), and the services that act for them — the
portal, a domain platform's member service — fetch it from the identity registry
with their own service token and forward it. So the credential alone proves only
that *some* service could read it, and any service that can read it can act as
that person on every route that accepts it.

This module adds the missing half: the request must also carry the **person's
own Keycloak access token** — which only a login produces — and the identity
registry must say that this login is bound to the subject the credential names.
The service asks with the person's token itself (``GET /users/me``), so it needs
no credential of its own for the question and learns nothing it could not
already learn from the login it holds.

    credential (who the dataspace says they are)
      + login token (who logged in, verified: signature, issuer, audience, expiry)
      + the registry's binding (realm, Keycloak user id) -> subject DID

**The key is the Keycloak user id** (`sub`), within the realm the token was
issued by. It is the one identifier an IdP does not let people change; email and
username are mutable, and the registry's own resolution cascade
(`identity_registry.api.v1.users.resolve_mapping`) calls the email a bootstrap
seed rather than an identity for that reason. The registry stores the pair as a
`keycloak_mappings` row, unique per (realm, user id), written by whoever
onboards the person (`POST /admin/keycloak/sync`).

This is not a holder proof in the VC sense — DCP's holder binding is
participant-only and its trust model excludes human presentation. It is OIDC
authentication with the credential as an attribute of the authenticated person.
See `docs/decisions/ADR-0024`.

**Posture.** ``required=None`` reads the environment: required everywhere except
``DS_ENV=dev``. When not required, a request without a person token is accepted
on the credential alone (the behaviour before this module) — but a person token
that *is* presented is always verified and always bound. A presented token that
fails is never ignored.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request

from .config import OidcConfig
from .fastapi import authenticate
from .jwt import get_bearer_token
from .production import is_production

log = logging.getLogger(__name__)

#: Positive answers are reused this long. A mapping changes only when a person
#: is re-provisioned or an operator unbinds them; the cost of the TTL is that an
#: unbinding takes this long to be seen by a process that has just asked.
DEFAULT_BINDING_CACHE_SECONDS = 60.0


class LoginBindingUnavailable(RuntimeError):
    """The registry could not answer. Never read as "not bound" or as "bound"."""


class LoginBindingLookup(Protocol):
    """Which subject DID is the login in *token* bound to — ``None`` for none.

    ``realm`` and ``user_id`` are what the caller already verified the token
    names; they key the cache, never the answer.
    """

    async def __call__(self, token: str, realm: str, user_id: str) -> str | None: ...


class IdentityRegistryLoginBinding:
    """Asks the identity registry, which holds the binding, **with the person's own token**.

    ``GET /users/me`` answers the DID the presented login is bound to, a 404
    when it is bound to none, and refuses a service token. The service forwards
    the token it was handed rather than authenticating as itself, so:

    - it needs no credential of its own for this, and no grant;
    - it can learn a person's DID only while it holds that person's login, so
      the route is no directory of who exists;
    - the registry verifies the token for **its own** audience. A person's token
      from the gateway carries every ds service's audience (the realm's
      `oauth2_proxy_client` mapper), the registry's included.
    """

    def __init__(
        self,
        base_url: str,
        *,
        ttl_seconds: float = DEFAULT_BINDING_CACHE_SECONDS,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._transport = transport
        self._cache: dict[tuple[str, str], tuple[float, str]] = {}

    async def __call__(self, token: str, realm: str, user_id: str) -> str | None:
        key = (realm, user_id)
        hit = self._cache.get(key)
        if hit is not None and hit[0] > time.monotonic():
            return hit[1]
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            if response.status_code == 404:
                # Bound to nobody. Not cached: it is the answer an operator is
                # about to fix by writing the mapping.
                return None
            response.raise_for_status()
            did = (response.json() or {}).get("did")
        except (httpx.HTTPError, ValueError) as exc:
            raise LoginBindingUnavailable(str(exc)) from exc
        if not isinstance(did, str) or not did:
            raise LoginBindingUnavailable("the registry named no subject")
        if self._ttl > 0:
            self._cache[key] = (time.monotonic() + self._ttl, did)
        return did

    def invalidate(self) -> None:
        self._cache.clear()


def realm_of(issuer_url: str | None) -> str | None:
    """The Keycloak realm an issuer URL names (``…/realms/<name>``), or ``None``."""
    if not issuer_url:
        return None
    segments = [s for s in urlsplit(issuer_url).path.split("/") if s]
    for i, segment in enumerate(segments[:-1]):
        if segment == "realms":
            return segments[i + 1]
    return None


def person_token_required(setting: bool | None) -> bool:
    """An explicit setting wins; unset means required everywhere but dev."""
    return is_production() if setting is None else setting


async def bind_login_token(
    request: Request,
    config: OidcConfig,
    subject_did: str,
    *,
    lookup: LoginBindingLookup | None,
    required: bool,
) -> str | None:
    """Prove the request carries the login token of the person *subject_did* names.

    Call it **after** the credential verified, with the DID the credential
    names. Returns the bound Keycloak user id, or ``None`` when nothing was
    bound because nothing had to be (not required, and no person token).

    Refusals: no token while required → 401; a token that does not verify → 401;
    a service token while required → 403; a person token for somebody else → 403;
    a registry that cannot answer, or no registry to ask, while a binding is
    needed → 503.
    """
    if not request.headers.get("Authorization"):
        if required:
            raise HTTPException(
                401,
                "This route acts for a person: send their own login token "
                "(Authorization: Bearer) with their credential",
            )
        return None

    # A presented token is always verified, required or not — issuer, audience,
    # signature, expiry — and a failure is a 401 rather than a fall-back to the
    # credential alone. Accepting a token that failed would make "send a broken
    # token" a way to skip the binding.
    principal = await authenticate(request, config)

    if principal.is_service:
        if required:
            raise HTTPException(
                403,
                "A service token cannot act for a person. Forward the person's "
                "own login token, or exchange it for one this service accepts",
            )
        log.warning(
            "Person route reached with a service token (%s) and a credential "
            "alone — accepted because the login-token binding is not required "
            "here (DS_ENV=dev or *_PERSON_TOKEN_REQUIRED=false)",
            principal.client_id or principal.subject,
        )
        return None

    user_id = principal.subject
    realm = realm_of(config.issuer_url) or realm_of(
        str(principal.claims.get("iss") or "")
    )
    if not user_id or not realm:
        raise HTTPException(
            401, "The login token names no Keycloak user and realm to bind"
        )
    if lookup is None:
        if required:
            log.error(
                "No identity registry is configured, so a person's login token "
                "cannot be bound to their credential — refusing."
            )
            raise HTTPException(503, "Login-token binding is not configured")
        log.warning(
            "Person token presented but no identity registry is configured to "
            "bind it — accepted on the credential alone (not required here)"
        )
        return None

    token = get_bearer_token(request.headers.get("Authorization"))
    try:
        bound_did = await lookup(token, realm, user_id)
    except LoginBindingUnavailable as exc:
        log.error("cannot bind login token to %s: %s", subject_did, exc)
        raise HTTPException(
            503, "The identity registry could not confirm whose login this is"
        ) from exc
    if bound_did != subject_did:
        raise HTTPException(
            403, "The login token does not belong to the credential's subject"
        )
    return user_id
