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

* **EDC's OAuth2 filter never checks ``aud``** (0.18.0: issuer, expiry, ``sub``
  and ``scope`` only). Any token of the realm whose ``sub`` names a participant
  context and whose ``scope`` matches passes. So these scopes are **optional**
  on an organisation client, requested only for the connector's EDC calls
  (``EDC_TOKEN_SCOPE``), together with ``EDC_MANAGEMENT_SCOPE``, which adds the
  audience ``EDC_MANAGEMENT_AUDIENCE``; ds's ``ManagementAudienceFilter`` in the
  EDC runtime refuses a management call without it. The token the connector
  sends to every other service carries neither: each token is good only where
  it is sent.
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

#: Grants nothing: requesting it adds `EDC_MANAGEMENT_AUDIENCE` to the token
#: (an audience mapper on the scope, `services/keycloak/clients.yaml`).
EDC_MANAGEMENT_SCOPE = "edc.management"

#: The audience the EDC management context requires (`ds.management.audience`).
EDC_MANAGEMENT_AUDIENCE = "svc-ds-edc"

#: The prefix of every client identity-registry provisions for an organisation.
ORGANISATION_CLIENT_PREFIX = "svc-ds-connector-"

#: The prefix of an organisation's **collector** client (`svc-ds-collector-<alias>`),
#: provisioned only for an organisation declared `collects_consent` (ADR-0026).
#: Same `sub` as the organisation client — the organisation's DID — and so the
#: same organisation identity (`Principal.organisation_context`), but a separate
#: secret held by whoever runs that organisation's onboarding, with **no default
#: scope, no client-level audience and no EDC power**: each grant is an optional
#: scope that adds exactly one audience, and the receiver checks it.
COLLECTOR_CLIENT_PREFIX = "svc-ds-collector-"

# ── The ds services' audiences ──────────────────────────────────────────────
#
# Every ds service verifies `aud` against its own client id (`OidcConfig.audience`).
IDENTITY_REGISTRY_AUDIENCE = "svc-ds-identity-registry"
CONNECTOR_AUDIENCE = "svc-ds-connector"
PROVENANCE_AUDIENCE = "svc-ds-provenance"

#: Every audience a ds service verifies. A collector token naming more than the
#: receiver's own is refused there: it was minted for more than one receiver, so
#: it is replayable at the other one (`ds_auth.audience`).
DS_SERVICE_AUDIENCES: tuple[str, ...] = (
    IDENTITY_REGISTRY_AUDIENCE,
    CONNECTOR_AUDIENCE,
    PROVENANCE_AUDIENCE,
    EDC_MANAGEMENT_AUDIENCE,
)

# ── The organisation-attributable acts ──────────────────────────────────────
#
# One audience per scope: each is declared in `services/keycloak/clients.yaml`
# with `audience:` set to the service that checks it, so requesting the scope is
# what puts that service in `aud`.

#: Register or delete a member of the caller's own organisation (identity-registry).
MEMBERSHIPS_WRITE_SCOPE = "identity-registry.memberships.write"
#: Issue, transition or revoke a data-subject credential linked to the caller's
#: own organisation (identity-registry).
CREDENTIALS_WRITE_SCOPE = "identity-registry.credentials.write"
#: Register a subject's standing decision (connector `POST /consent/admin/shares`,
#: `POST /consent/request`).
CONSENT_PROVISION_SCOPE = "connector.consent.provision"
#: Read back what the caller registered (connector `GET /consent/admin/subject-shares`,
#: `GET /consent/admin/decisions`). A read never needs the write grant.
CONSENT_COLLECTOR_READ_SCOPE = "connector.consent.collector.read"
#: Who consents to an offer (connector `GET /consent/admin/shares`).
CONSENT_AUDIENCE_SCOPE = "connector.consent.audience"
#: Record data leaving the platform (connector `POST /admin/disclosure`).
DISCLOSURE_RECORD_SCOPE = "connector.disclosure.record"
#: Publish the organisation's own catalogue (connector `POST /provider/sync`, …).
PROVIDER_WRITE_SCOPE = "connector.provider.write"
#: Write provenance events (provenance).
PROVENANCE_WRITE_SCOPE = "provenance.write"

#: The audience each audience-bound scope adds — the value its receiver requires.
SCOPE_AUDIENCES: dict[str, str] = {
    MEMBERSHIPS_WRITE_SCOPE: IDENTITY_REGISTRY_AUDIENCE,
    CREDENTIALS_WRITE_SCOPE: IDENTITY_REGISTRY_AUDIENCE,
    CONSENT_PROVISION_SCOPE: CONNECTOR_AUDIENCE,
    CONSENT_COLLECTOR_READ_SCOPE: CONNECTOR_AUDIENCE,
    CONSENT_AUDIENCE_SCOPE: CONNECTOR_AUDIENCE,
    DISCLOSURE_RECORD_SCOPE: CONNECTOR_AUDIENCE,
    PROVIDER_WRITE_SCOPE: CONNECTOR_AUDIENCE,
    PROVENANCE_WRITE_SCOPE: PROVENANCE_AUDIENCE,
    EDC_MANAGEMENT_SCOPE: EDC_MANAGEMENT_AUDIENCE,
}

#: What a connector needs from ds's other services, in **every** token its
#: organisation's client mints. `svc-ds-connector` in `clients.yaml` holds nothing
#: any more — it is the audience connectors verify — so this is the one list, read
#: by identity-registry when it provisions an organisation client (its image does
#: not ship `clients.yaml`).
#:
#: **Nothing here is an act a counterparty could replay.** The connector sends its
#: default token to identity-registry, provenance and the counterparty's
#: connector (`GET /consent/pending`). `connector.consent.provision` and
#: `connector.provider.write` used to be here, so a counterparty that received
#: that token could register consent at, or publish to, any connector that
#: accepted this organisation. They are optional now (`ORGANISATION_ACTION_SCOPES`).
CONNECTOR_SERVICE_SCOPES: tuple[str, ...] = (
    "identity-registry.read",
    "identity-registry.membership.read",
    # A sharing offer may admit by credential type (`circle.py`).
    "identity-registry.credentials.read",
    "provenance.write",
    # A consumer connector asks the provider whether its negotiation is parked
    # on a consent decision (`GET /consent/pending`).
    "connector.consent.read",
    # The holder reads the data keys its own data plane serves, per offer, and
    # their history (ADR-0022). Every organisation client holds it; the bound is
    # in the connector, which accepts only its own organisation's client and
    # refuses a collector, as `_own_participant_only` refuses a foreign publish.
    "connector.consent.holder.read",
    # Read-back. A publisher that cannot list what it published cannot tell
    # whether it worked — which is how a live deployment's publishing path stayed
    # broken, and green, for a fortnight.
    "connector.provider.read",
)

#: What the organisation client may **ask for**, one act at a time (ADR-0026).
#:
#: * `connector.consent.provision` — the organisation registers its members'
#:   consent, at its own connector or at a holder that accepts it as a collector
#:   (plan `a-collector-registers-consent-at-the-holder`), and
#:   `connector.consent.collector.read` reads it back;
#: * `connector.provider.write` — it publishes **its own** catalogue
#:   (`POST /provider/sync`; ADR-0014 decision 2, amended). Bounded by the
#:   connector's `_own_participant_only` perimeter, not here.
ORGANISATION_ACTION_SCOPES: tuple[str, ...] = (
    CONSENT_PROVISION_SCOPE,
    CONSENT_COLLECTOR_READ_SCOPE,
    PROVIDER_WRITE_SCOPE,
)

#: The services a connector's token must be accepted by — every ds service
#: verifies `aud`, so a client without these authenticates and is refused.
CONNECTOR_AUDIENCES: tuple[str, ...] = (
    IDENTITY_REGISTRY_AUDIENCE,
    PROVENANCE_AUDIENCE,
    # The counterparty connector — the audience of `GET /consent/pending`.
    CONNECTOR_AUDIENCE,
)

#: In every token the organisation client mints.
ORGANISATION_CLIENT_DEFAULT_SCOPES: tuple[str, ...] = CONNECTOR_SERVICE_SCOPES

#: Only in a token that asks for them: the connector's EDC token, and the
#: organisation's own acts.
ORGANISATION_CLIENT_OPTIONAL_SCOPES: tuple[str, ...] = (
    *MANAGEMENT_API_SCOPES,
    EDC_MANAGEMENT_SCOPE,
    *ORGANISATION_ACTION_SCOPES,
)

#: The `scope` parameter of the connector's EDC token request. **Stated, not
#: derived**: it used to join every optional scope, so each new optional grant
#: would have ridden along in the token the connector hands its EDC.
EDC_TOKEN_SCOPE = " ".join((*MANAGEMENT_API_SCOPES, EDC_MANAGEMENT_SCOPE))

#: Everything an organisation client holds, default and optional.
ORGANISATION_CLIENT_SCOPES: tuple[str, ...] = (
    *ORGANISATION_CLIENT_DEFAULT_SCOPES,
    *ORGANISATION_CLIENT_OPTIONAL_SCOPES,
)

#: A collector client holds no default scope: a token asked for nothing carries
#: no ds audience and is refused by every ds service.
COLLECTOR_CLIENT_DEFAULT_SCOPES: tuple[str, ...] = ()

#: Each requested **alone** (one scope, one audience, one receiver). The last four
#: moved here from the plain `svc-ds-onboarding` client, so no secret is shared
#: across onboarding operators and every act is attributable to an organisation.
COLLECTOR_CLIENT_OPTIONAL_SCOPES: tuple[str, ...] = (
    MEMBERSHIPS_WRITE_SCOPE,
    CONSENT_PROVISION_SCOPE,
    CONSENT_COLLECTOR_READ_SCOPE,
    CREDENTIALS_WRITE_SCOPE,
    CONSENT_AUDIENCE_SCOPE,
    DISCLOSURE_RECORD_SCOPE,
    PROVENANCE_WRITE_SCOPE,
)

#: The grants the plain `svc-ds-onboarding` client held for acts that belong to an
#: organisation. Presented by a plain service token they are accepted only under
#: `DS_ENV=dev`, logged, as a transition (`ds_auth.audience.plain_service_transition`).
ONBOARDING_TRANSITION_SCOPES: tuple[str, ...] = (
    CREDENTIALS_WRITE_SCOPE,
    CONSENT_AUDIENCE_SCOPE,
    DISCLOSURE_RECORD_SCOPE,
    PROVENANCE_WRITE_SCOPE,
)


def is_management_api_scope(scope: str) -> bool:
    """Whether *scope* is in EDC's management-API namespace, in any form."""
    return scope == NAMESPACE or scope.startswith(f"{NAMESPACE}:")


def organisation_client_id(alias: str) -> str:
    """The client an organisation's connector and agents authenticate as."""
    return f"{ORGANISATION_CLIENT_PREFIX}{alias}"


def collector_client_id(alias: str) -> str:
    """The client an organisation's onboarding authenticates as (ADR-0026)."""
    return f"{COLLECTOR_CLIENT_PREFIX}{alias}"


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
