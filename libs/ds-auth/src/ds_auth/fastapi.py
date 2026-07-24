"""FastAPI integration — the ``require_permission`` dependency.

Requires the optional ``fastapi`` extra: ``pip install ds-auth[fastapi]``.

Each service stores an :class:`~ds_auth.config.OidcConfig` on
``app.state.oidc_config`` at startup; the dependency reads it from the request.
"""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request

from .config import OidcConfig
from .errors import AuthConfigError, PermissionDenied, TokenInvalid, TokenMissing
from .jwt import get_bearer_token, verify_token
from .principal import Principal

# perimeter(principal, request) -> bool | Awaitable[bool]
PerimeterFn = Callable[[Principal, Request], bool | Awaitable[bool]]


def get_oidc_config(request: Request) -> OidcConfig:
    config = getattr(request.app.state, "oidc_config", None)
    if not isinstance(config, OidcConfig):
        # Server misconfiguration — the app forgot to set app.state.oidc_config.
        raise HTTPException(status_code=500, detail="Auth is not configured")
    return config


async def authenticate(request: Request, config: OidcConfig) -> Principal:
    """Verify the request's bearer token and return the caller's Principal."""
    try:
        token = get_bearer_token(request.headers.get("Authorization"))
        claims = verify_token(token, config)
    except TokenMissing as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except TokenInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Principal.from_claims(claims)


def require_exact_permission(
    *perms: str,
    perimeter: PerimeterFn | None = None,
) -> Callable[..., Awaitable[Principal]]:
    """Like :func:`require_permission`, but ``{service}.admin`` does **not** satisfy it.

    For permissions that mean "I am this component" rather than "I may
    administer this component": accepting EDC webhook callbacks, reading EDR
    signing keys over the internal API. An operator holding ``connector.admin``
    should not be able to forge a transfer-state callback or lift the keys that
    sign data-plane tokens, and a service client that happens to carry an admin
    scope should not silently acquire either.

    The permission has to be granted by name, which also makes it visible in the
    realm config: you can read off exactly which client is allowed to be the EDC.
    """
    if not perms:
        raise ValueError("require_exact_permission needs at least one permission")

    async def _dependency(
        request: Request,
        config: OidcConfig = Depends(get_oidc_config),
    ) -> Principal:
        principal = await authenticate(request, config)

        if not principal.grants_exactly(perms):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {' or '.join(perms)}",
            )

        await _check_perimeter(perimeter, principal, request)
        return principal

    return _dependency


async def _check_perimeter(
    perimeter: PerimeterFn | None, principal: Principal, request: Request
) -> None:
    if perimeter is None:
        return
    try:
        result = perimeter(principal, request)
        if inspect.isawaitable(result):
            result = await result
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=403, detail="Outside permitted perimeter")


def require_permission(
    *perms: str,
    perimeter: PerimeterFn | None = None,
) -> Callable[..., Awaitable[Principal]]:
    """Dependency factory: require *any* of ``perms``, then an optional perimeter.

    ``perms`` are permission strings (``connector.provider.write``). A service
    token satisfies them via its scopes, a user token via its groups —
    ``{service}.admin`` is a superset.

    ``perimeter`` optionally narrows an already-permitted principal to the
    subset of resources it may touch (e.g. its own participant/subject),
    turning coarse permission into bounded authority. It returns True to allow.
    """
    if not perms:
        raise ValueError("require_permission needs at least one permission")

    async def _dependency(
        request: Request,
        config: OidcConfig = Depends(get_oidc_config),
    ) -> Principal:
        principal = await authenticate(request, config)

        if not principal.grants_any(perms):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {' or '.join(perms)}",
            )

        await _check_perimeter(perimeter, principal, request)
        return principal

    return _dependency
