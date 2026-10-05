"""One audience per scope, checked by the receiver (ADR-0026).

An optional scope keeps a grant out of the tokens that do not ask for it, and it
does not stop **replay**: a token asked for `connector.consent.provision` and
sent to one connector is as good at the next connector, or at identity-registry,
if it names them. EDC binds a token between participants the same way ds does
here — the self-issued token's `aud` is the counterparty, and the counterparty
refuses any other (`SelfIssueIdTokenValidationAction`, DCP v1.0) — so ds copies
the pattern rather than inventing one:

* each organisation-attributable scope is declared with **one audience**
  (`services/keycloak/clients.yaml`, `management_api.SCOPE_AUDIENCES`), so
  requesting it is what puts its receiver in `aud`;
* the **receiver** requires its own audience on these calls
  (:func:`check_audience_bound`) — not only through `verify_token`, which skips
  `aud` where no issuer is configured, but on the route that does the act;
* a **collector** token (`svc-ds-collector-<alias>`) has no client-level audience
  at all, so one that names another ds service besides the receiver was asked
  for more than one act and is refused: the rule is one scope per token.

And the plain `svc-ds-onboarding` grants that act for an organisation move to the
collector client. Presented by a plain service token they keep working only under
``DS_ENV=dev``, logged, as a transition (:func:`plain_service_transition`).
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .errors import PermissionDenied
from .management_api import DS_SERVICE_AUDIENCES
from .principal import Principal
from .production import is_production

log = logging.getLogger(__name__)

Perimeter = Callable[[Principal, Any], bool | Awaitable[bool]]


def own_audience(request: Any) -> str | None:
    """The audience this service verifies (`OidcConfig.audience`), or ``None``."""
    config = getattr(getattr(request, "app", None), "state", None)
    config = getattr(config, "oidc_config", None)
    return getattr(config, "audience", None) or None


def check_audience_bound(principal: Principal, audience: str | None) -> None:
    """Refuse a service token not minted for *audience*, or minted for more.

    Applies to service tokens only: a person's authority is their groups, not a
    requested scope, and their token's `aud` is the realm's to set. Raises
    :class:`PermissionDenied`; a route turns that into a 403.
    """
    if not principal.is_service:
        return
    if not audience:
        # Fail closed: a receiver that cannot name itself cannot tell whether
        # the token was meant for it.
        raise PermissionDenied(
            "this service has no audience configured, so it cannot check that the "
            "token was minted for it"
        )
    held = principal.audiences
    if audience not in held:
        raise PermissionDenied(
            f"the token was not minted for this service: its aud does not name "
            f"{audience!r} — request the scope whose audience is this service"
        )
    if principal.is_collector:
        foreign = sorted(a for a in held if a in DS_SERVICE_AUDIENCES and a != audience)
        if foreign:
            raise PermissionDenied(
                "a collector token is asked for one act at a time: this one also "
                f"names {', '.join(foreign)}, so it would be good there too"
            )


def audience_bound(perimeter: Perimeter | None = None) -> Perimeter:
    """A `require_permission` perimeter: the audience check, then *perimeter*."""

    async def _perimeter(principal: Principal, request: Any) -> bool:
        check_audience_bound(principal, own_audience(request))
        if perimeter is None:
            return True
        result = perimeter(principal, request)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    return _perimeter


def plain_service_transition(principal: Principal, act: str) -> None:
    """A plain service token doing an organisation's *act*: dev only, logged.

    The grants `svc-ds-onboarding` held for acts that belong to one organisation
    (credential issuance, the offer audience read, disclosure records,
    provenance writes) moved to that organisation's collector client. A plain
    service names no organisation, so outside ``DS_ENV=dev`` it is refused; in
    dev it is accepted and a warning names the client, so the transition is
    visible until the caller moves. Organisations and persons pass untouched.
    """
    if not principal.is_service or principal.is_organisation:
        return
    client = principal.client_id or principal.subject or "<unknown client>"
    if is_production():
        raise PermissionDenied(
            f"{act} is an organisation's act: a plain service token ({client}) "
            "names no organisation. Use the organisation's collector client "
            "(svc-ds-collector-<alias>) — a plain service is accepted only under "
            "DS_ENV=dev, as a transition"
        )
    log.warning(
        "TRANSITION (DS_ENV=dev only): plain service client %s performed %s; "
        "refused outside dev — move it to svc-ds-collector-<alias>",
        client,
        act,
    )


def transition_bound(act: str, perimeter: Perimeter | None = None) -> Perimeter:
    """A `require_permission` perimeter: audience, the plain-service transition,
    then *perimeter*."""

    async def _perimeter(principal: Principal, request: Any) -> bool:
        check_audience_bound(principal, own_audience(request))
        plain_service_transition(principal, act)
        if perimeter is None:
            return True
        result = perimeter(principal, request)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    return _perimeter
