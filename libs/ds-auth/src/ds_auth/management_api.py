"""EDC's management-API scopes, as far as ds grants them.

EDC 0.18.0's v5 management API authorises with its own grammar,
``management-api[:resource]:read|write|admin`` (``Scope``, ``ScopeMatcher`` and
``ManagementApiScopes`` in EDC's ``auth-spi``), not with ds's
``service.resource.action``. The two never satisfy each other:
``grant_satisfies`` only widens a grant ending in ``.admin``.

This is the one list of the ones ds grants, and it is granted to **organisation
clients only** (``svc-ds-connector-<alias>``, provisioned by identity-registry
with a ``sub`` mapper naming the organisation's participant context). Two
properties of EDC make the list a security boundary rather than a convenience:

* **EDC's OAuth2 filter never checks ``aud``.** Any token of the realm whose
  ``sub`` names a participant context and whose ``scope`` matches passes, so a
  client holding one of these scopes can act on that context's management API.
  Who holds them is decided here and in the realm, nowhere else.
* **``admin`` is cross-tenant elevation** and makes ``sub`` irrelevant
  (``ServicePrincipalAuthenticationFilter``). No ds client is ever granted it,
  and neither is a ``*`` resource.

Each entry is the scope the v5 controller for a resource ds calls requires
(``@RequiredScope``), at the strongest action ds needs; ``write`` satisfies
``read``. ds calls no other v5 resource.
"""

from __future__ import annotations

from collections.abc import Iterable

#: The namespace EDC reserves (``ManagementApiScopes.NAMESPACE``).
NAMESPACE = "management-api"

#: What an organisation client is granted. Per resource, never a wildcard.
MANAGEMENT_API_SCOPES: tuple[str, ...] = (
    # provider: publish offers
    "management-api:assets:write",
    "management-api:policies:write",
    "management-api:contractdefinitions:write",
    # consumer: find, negotiate, pull. `negotiations:write` also guards ds's own
    # resume route on the management context.
    "management-api:catalog:read",
    "management-api:negotiations:write",
    "management-api:agreements:read",
    "management-api:transfers:write",
)

#: The prefix of every client identity-registry provisions for an organisation.
ORGANISATION_CLIENT_PREFIX = "svc-ds-connector-"

#: What a connector needs from ds's other services, held by its organisation's
#: client. `svc-ds-connector` in `clients.yaml` holds nothing any more — it is the
#: audience connectors verify — so this is the one list, read by
#: identity-registry when it provisions an organisation client (its image does
#: not ship `clients.yaml`).
CONNECTOR_SERVICE_SCOPES: tuple[str, ...] = (
    "identity-registry.read",
    "identity-registry.membership.read",
    # A sharing offer may admit by credential type (`circle.py`).
    "identity-registry.credentials.read",
    "provenance.write",
    # A consumer connector asks the provider whether its negotiation is parked
    # on a consent decision (`GET /consent/pending`).
    "connector.consent.read",
)

#: The services a connector's token must be accepted by — every ds service
#: verifies `aud`, so a client without these authenticates and is refused.
CONNECTOR_AUDIENCES: tuple[str, ...] = (
    "svc-ds-identity-registry",
    "svc-ds-provenance",
    # The counterparty connector — the audience of `GET /consent/pending`.
    "svc-ds-connector",
)

#: Everything an organisation client holds.
ORGANISATION_CLIENT_SCOPES: tuple[str, ...] = (
    *CONNECTOR_SERVICE_SCOPES,
    *MANAGEMENT_API_SCOPES,
)


def is_management_api_scope(scope: str) -> bool:
    """Whether *scope* is in EDC's management-API namespace, in any form."""
    return scope == NAMESPACE or scope.startswith(f"{NAMESPACE}:")


def organisation_client_id(alias: str) -> str:
    """The client an organisation's connector and agents authenticate as."""
    return f"{ORGANISATION_CLIENT_PREFIX}{alias}"


_ACTION_LEVEL = {"read": 0, "write": 1, "admin": 2}


def _parse(scope: str) -> tuple[str, str, int] | None:
    """EDC's `Scope.parse`: `prefix[:resource]:action`; ``None`` if malformed."""
    parts = scope.strip().split(":")
    if len(parts) not in (2, 3) or not all(parts):
        return None
    level = _ACTION_LEVEL.get(parts[-1].lower())
    if level is None:
        return None
    resource = parts[1] if len(parts) == 3 else "*"
    return parts[0], resource, level


def scope_satisfies(granted: Iterable[str], required: str) -> bool:
    """EDC's `ScopeMatcher.isSatisfiedBy`, for a ds route guarding by EDC scope.

    A granted scope satisfies ``required`` when the prefixes match, its resource
    is the same or ``*``, and its action is at least as strong
    (``admin`` ⊇ ``write`` ⊇ ``read``). Unparseable entries grant nothing, and a
    malformed requirement is satisfied by nothing — the same two rules EDC
    applies, so a ds route and the EDC call behind it agree on who may call.
    """
    want = _parse(required)
    if want is None:
        return False
    for entry in granted:
        have = _parse(entry)
        if have is None:
            continue
        if have[0] == want[0] and have[1] in (want[1], "*") and have[2] >= want[2]:
            return True
    return False
