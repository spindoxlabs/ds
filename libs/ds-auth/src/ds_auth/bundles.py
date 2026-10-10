"""Role bundles — the user-authority vocabulary, and its expansion (Layer A).

A service token carries its authority as **scopes**, minted from
``services/keycloak/clients.yaml``. A user token carries it as **groups**. Those
two vocabularies used to be the *same strings*: ~30 Keycloak groups whose names
mirrored the scope names exactly.

That cost more than it bought. The scope vocabulary is ds's internal API surface
— one name per endpoint family, growing with every route. The group vocabulary
**crosses an organisational boundary**: it is the one thing an operator who does
not administer the realm has to be asked to create. Mirroring the two forced a ds
implementation detail into somebody else's IAM, and made the permission model
work only where ds administers the realm. Practically, it also meant group
provisioning happened by realm import — i.e. only when the Keycloak database was
empty — so a new permission could not be granted to a human on a running system
at all.

So a user's groups name a **role bundle**, and this module expands a bundle into
the capability set it stands for. Four names instead of thirty; adding an endpoint
is a ds release rather than a change request against a realm.

What deliberately does **not** change: :attr:`ds_auth.Principal.authority` still
resolves to one flat grant list, so a route asks for
``require_permission("connector.provider.write")`` and never learns which kind of
token satisfied it.

**This table is ds's own semantics and lives in ds's code.** It is not deployment
configuration: a permission table that can be edited at deploy time is a
privilege-escalation surface, and this one is small enough to review. Mapping
*someone else's* group names onto these bundles is a separate concern (Layer B),
because that is about a foreign IAM's naming rather than about what ds permits.

**Two levels, and nothing in between.** A bundle is granted at exactly one level:

* **platform** — by a Keycloak **realm role** from an explicit allowlist
  (:data:`REALM_ROLE_BUNDLES`). ``platform-admin`` is the platform administrator.
  Read from ``realm_access.roles`` only: never from the ``groups`` claim, never from
  another client's ``resource_access`` roles.
* **organisation** — by a group *inside* one organisation
  (``organization.<alias>.groups``), valid for that organisation only.

A realm-level **group** grants nothing at all, and an organisation group can never
reach a platform bundle or a ``{service}.admin`` superset — that is what used to make
an organisation group named ``ds-admin`` a deployment-wide grant. The portal's
TypeScript twin is generated from this module (``bundles_export.py``), so the UI and
the API read a token the same way by construction.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping

from .management_api import MANAGEMENT_API_SCOPES, ORGANISATION_READ_SCOPES

logger = logging.getLogger(__name__)

# ── Machine identity ─────────────────────────────────────────────────────────
#
# Permissions that mean "I *am* this component", not "I may act on this
# resource". They are checked with `has_exact_permission`, so the
# `{service}.admin` superset never satisfies them (see permissions.py). No human
# role may carry them either: accepting EDC webhook callbacks or reading the EDR
# signing keys is not a privilege an administrator inherits by being an
# administrator.
MACHINE_IDENTITY_PERMISSIONS: frozenset[str] = frozenset(
    {
        "connector.internal",
        "connector.webhook",
    }
)

# ── Layer A: bundle → capabilities ───────────────────────────────────────────
#
# `{service}.admin` appears here and nowhere else in a granted position. It is
# legitimate for an interactive, revocable human operator and wrong for a
# long-lived process, which is why service clients enumerate their grants
# instead (clients.yaml). Note `connector.admin` still cannot reach
# `connector.internal` or `connector.webhook` — the exact-permission rule holds
# regardless of who is asking.
ROLE_BUNDLES: dict[str, tuple[str, ...]] = {
    # The dataspace operator: runs the authority, holds the irreversible acts.
    # `identity-registry.admin` covers organisation promotion, which is
    # deliberately not delegated to the onboarding reviewer below.
    "ds-admin": (
        "identity-registry.admin",
        "connector.admin",
        "provenance.read",
        "provenance.write",
        "catalog.read",
    ),
    # A participant's own operator console: publish datasets, run the provider,
    # record an offline handover, see the negotiation history.
    #
    # **No `connector.consent.provision`** (plan
    # `a-collector-registers-consent-at-the-holder`, decision 5, 2026-09-17). A
    # participant seat is not bound to a connector, so the grant let any
    # participant's operator register consent at any connector, for anyone's
    # members. Consent is registered by an organisation's own client (an
    # accepted collector, or the holder itself); a person overriding a
    # withdrawal is the deployment operator, through `connector.admin`.
    "ds-participant-admin": (
        "connector.provider.read",
        "connector.provider.write",
        "connector.history.read",
        "connector.registry.invalidate",
        "connector.ingestion.record",
        "connector.disclosure.record",
        "catalog.read",
        "provenance.read",
        "identity-registry.read",
        "identity-registry.membership.read",
    ),
    # Read-only over the same surface — the auditor / analyst seat. A read-only
    # operator should see the queue without buttons that would 403.
    "ds-participant-viewer": (
        "connector.provider.read",
        "connector.history.read",
        "catalog.read",
        "provenance.read",
        "identity-registry.read",
    ),
    # Reviews organisation applications and service agreements. Prepares a
    # promotion; does not commit it — `identity-registry.organizations.promote`
    # is the irreversible act that turns an applicant into a DSP counterparty,
    # and it stays with `ds-admin`.
    "ds-onboarding-operator": (
        "identity-registry.organizations.read",
        "identity-registry.organizations.write",
        "identity-registry.agreements.read",
        "identity-registry.participants.write",
        "identity-registry.read",
    ),
    # An authenticated human with no operator authority: they may browse the
    # catalogue, and that is the whole of their group-plane authority.
    #
    # This deliberately collapses "consumer user" and "data subject" into one
    # seat, because the difference between them is a **credential**, not a
    # permission: consent management and consumer actions authenticate with a
    # VC-JWT verified against the trust anchor (`/consent/my/*`, `/consumer/*`),
    # not with `require_permission`. A person legitimately holds both roles at
    # once, which a group-based split would model as mutually exclusive.
    "ds-member": ("catalog.read",),
}

# ── The two levels ───────────────────────────────────────────────────────────
#
# Every bundle is granted at exactly one level. `test_two_levels.py` asserts the
# two sets partition `ROLE_BUNDLES`, so a new bundle cannot be added without
# deciding where it may be granted.

#: The realm role that makes a person the platform administrator. The same name
#: celine-sdk exports as ``PLATFORM_ADMIN_ROLE``; mirrored, not imported.
PLATFORM_ADMIN_ROLE = "platform-admin"

#: Deployment-wide seats. Granted **only** by a realm role in
#: :data:`REALM_ROLE_BUNDLES`; an organisation group naming one grants nothing.
PLATFORM_BUNDLES: frozenset[str] = frozenset({"ds-admin", "ds-onboarding-operator"})

#: Seats that only mean something *for an organisation*. Granted **only** by a
#: group inside that organisation; a realm role naming one grants nothing.
ORGANISATION_BUNDLES: frozenset[str] = frozenset(
    {"ds-participant-admin", "ds-participant-viewer", "ds-member"}
)

#: The explicit allowlist: realm role → platform bundle. A realm role not listed
#: here grants nothing (`offline_access`, `default-roles-<realm>`, a retired
#: `admin` …), and so does every client's `resource_access` role.
#:
#: `ds-onboarding-operator` is the one platform seat besides the administrator:
#: it reviews organisation applications, which is the dataspace authority's job
#: and not any one organisation's, and it deliberately stops short of promotion.
REALM_ROLE_BUNDLES: dict[str, str] = {
    PLATFORM_ADMIN_ROLE: "ds-admin",
    "ds-onboarding-operator": "ds-onboarding-operator",
}

#: Literal permissions an organisation group may name directly, besides a
#: bundle name. Everything an organisation bundle grants, plus:
#:
#: * ``connector.consent.holder.read`` — a person granted the holder's key list
#:   *for one organisation* (ADR-0022); the connector checks the organisation.
#:
#: Anything else an organisation group names grants nothing: no
#: ``{service}.admin`` superset, no platform-only permission, no machine identity.
ORGANISATION_PERMISSIONS: frozenset[str] = frozenset(
    {
        *(p for b in sorted(ORGANISATION_BUNDLES) for p in ROLE_BUNDLES[b]),
        "connector.consent.holder.read",
    }
)


# ── Permissions no bundle expands to, on purpose ─────────────────────────────
#
# Declared rather than left implicit, so `test_vocabulary.py` can assert that
# every scope in clients.yaml is either reachable by a human or listed here. A
# scope that is neither is a scope nobody can be granted — most likely an
# oversight in the bundle table.
SERVICE_ONLY_PERMISSIONS: frozenset[str] = frozenset(
    {
        # Machine identity, restated for the coverage test's benefit.
        *MACHINE_IDENTITY_PERMISSIONS,
        # Consumer connector → provider connector. Participant-to-participant,
        # never a person.
        "connector.consent.read",
        # The organisation client's EDC token: grants nothing, adds the EDC
        # management audience (`management_api.EDC_MANAGEMENT_SCOPE`).
        "edc.management",
        # Federated catalogue → consumer connector. A person reaching
        # POST /consumer/catalog authenticates with a ConsumerUser VC-JWT, not
        # with a group, so no bundle expands to this.
        "connector.consumer.read",
        # The onboarding funnel's three narrow grants. A human operator reaches
        # the same endpoints through `identity-registry.admin` in `ds-admin`.
        "identity-registry.credentials.write",
        "identity-registry.memberships.write",
        "identity-registry.keycloak.sync",
        # Connector → identity-registry, evaluating a sharing offer's
        # `admitted_by`. No page asks it: a person reaching the same fact does so
        # through `identity-registry.admin` in `ds-admin`.
        "identity-registry.credentials.read",
        # Email → subject-id resolution, used by the funnel to mint an identity.
        "identity-registry.resolve",
        # Organisation promotion: reachable by a human, but only through
        # `identity-registry.admin`. Listed so the coverage test does not report
        # it as unreachable.
        "identity-registry.organizations.promote",
        # Which organisations a holder accepts consent registrations from. A
        # governance act about two organisations: reachable by a human through
        # `identity-registry.admin` only, like promotion.
        "identity-registry.collectors.write",
        # Register a subject's consent decision at a connector. Requested by an
        # organisation's own clients only (`management_api.ORGANISATION_ACTION_SCOPES`
        # and the collector client, ADR-0026) — the connector refuses any other
        # service token — and reachable by a human only through
        # `connector.admin`. Out of `ds-participant-admin` since 2026-09-17.
        "connector.consent.provision",
        # Read back what the caller registered (`GET /consent/admin/subject-shares`,
        # `/decisions`), without a write grant (ADR-0026). Same holders as
        # `.provision`; a human reaches it through `connector.admin` only.
        "connector.consent.collector.read",
        # "Who consents to this offer" — the cross-subject read behind
        # `GET /consent/admin/shares`. Held by onboarding, and reachable by a
        # human, but only through `connector.admin` in `ds-admin` — deliberately
        # *not* in `ds-participant-admin`, so a participant operator does not
        # acquire bulk subject enumeration. Listed here for the same reason as
        # the promote scope above: reachable only through an admin superset, so
        # the coverage test would otherwise report it as a permission nobody can
        # be granted.
        "connector.consent.audience",
        # The holder's key list and history (ADR-0022). Held by organisation
        # clients (`management_api.CONNECTOR_SERVICE_SCOPES`), and reachable by a
        # human only through `connector.admin` — deliberately not in
        # `ds-participant-admin`, for the reason `.audience` is not: a key list
        # is a roster of authorised households, and nobody should hold one as a
        # side effect of an operator seat.
        "connector.consent.holder.read",
        # Not ds endpoints — `dataset.*` belongs to the data-plane service, and is
        # here only because ds service clients call it.
        #
        # A *domain backend's* scopes are not listed at all, and deliberately:
        # they live in a `clients.<domain>.yaml` overlay rather than in ds's core
        # declaration, so naming them here would put a domain vocabulary back into
        # ds's code — and would fail this list's own staleness check in any
        # deployment that runs a different backend, or none.
        "dataset.admin",
        "dataset.query",
        "dataset.read",
        "dataset.write",
        # EDC's management-API scopes. Not ds permissions either — EDC's own
        # grammar — and granted to organisation clients only, never to a person
        # and never through a bundle (`management_api.py`).
        *MANAGEMENT_API_SCOPES,
        *ORGANISATION_READ_SCOPES,
    }
)


def bundle_capabilities(bundle: str) -> tuple[str, ...]:
    """The capabilities ``bundle`` stands for, or ``()`` if it is not a bundle."""
    return ROLE_BUNDLES.get(bundle, ())


def all_bundled_permissions() -> frozenset[str]:
    """Every permission reachable through some bundle."""
    return frozenset(p for caps in ROLE_BUNDLES.values() for p in caps)


def parse_group_aliases(raw: str | None) -> dict[str, str]:
    """Parse and **validate** a Layer B alias map from its JSON env form.

    Layer B maps a *foreign* IdP's **organisation group** names onto ds
    organisation bundles::

        {"celine-manager": "ds-participant-admin",
         "celine-viewer": "ds-participant-viewer"}

    The values must be **organisation bundle names**, never capabilities and never
    a platform bundle. An alias pointing straight at ``connector.provider.write``
    would make deployment configuration a permission table, which is the thing
    Layer A exists to prevent; one pointing at ``ds-admin`` would make an
    organisation group a platform grant, which is the thing the two levels exist
    to prevent. Either is dropped and named in the log rather than honoured.
    Dropping is the safe direction: the group then grants nothing.

    Malformed JSON yields an empty map and a loud error. That is deliberate: a
    typo'd alias map must not silently become a *different* map, and an empty one
    means "no translation", which is the pre-existing behaviour.
    """
    if not raw or not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.error(
            "ds-auth: group alias map is not valid JSON (%s) — no aliases applied. "
            'Expected {"foreign-group": "ds-bundle"}.',
            exc,
        )
        return {}

    if not isinstance(parsed, dict):
        logger.error(
            "ds-auth: group alias map must be a JSON object, got %s — no aliases "
            "applied.",
            type(parsed).__name__,
        )
        return {}

    aliases: dict[str, str] = {}
    for foreign, target in parsed.items():
        if not isinstance(foreign, str) or not isinstance(target, str):
            logger.error(
                "ds-auth: ignoring non-string alias entry %r -> %r", foreign, target
            )
            continue
        if target not in ORGANISATION_BUNDLES:
            logger.error(
                "ds-auth: ignoring alias %r -> %r: %r is not an organisation role "
                "bundle. An alias may only name one of %s — never a capability, and "
                "never a platform bundle, which only a realm role grants.",
                foreign,
                target,
                target,
                ", ".join(sorted(ORGANISATION_BUNDLES)),
            )
            continue
        aliases[foreign] = target

    if aliases:
        logger.info(
            "ds-auth: group alias map active — %s",
            ", ".join(f"{k} -> {v}" for k, v in sorted(aliases.items())),
        )
    return aliases


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


def platform_authority(realm_roles: Iterable[str]) -> tuple[str, ...]:
    """The capabilities a person's **realm roles** grant, deployment-wide.

    Only a role in :data:`REALM_ROLE_BUNDLES` counts, and it expands to its
    platform bundle. Every other role grants nothing — there is no pass-through
    at this level, so a realm role that happens to be named like a permission
    (``connector.admin``) is not one.
    """
    capabilities: list[str] = []
    for role in realm_roles:
        if not isinstance(role, str):
            continue
        bundle = REALM_ROLE_BUNDLES.get(role)
        if bundle is not None:
            capabilities.extend(ROLE_BUNDLES[bundle])
    return _ordered_unique(capabilities)


def organisation_authority(
    groups: Iterable[str], aliases: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """The capabilities one organisation's groups grant, **within** it.

    Three rules per group, in order:

    0. a **Layer B alias** translates a foreign group name into an organisation
       bundle (validated at parse time; :func:`parse_group_aliases`);
    1. an **organisation bundle** expands into its capabilities;
    2. a name in :data:`ORGANISATION_PERMISSIONS` grants itself.

    Anything else grants nothing — a platform bundle (``ds-admin``), a
    ``{service}.admin`` superset, a machine identity, a permission only the
    platform holds, or an unrecognised name. That is the whole difference from the
    flat expansion this replaced, whose rule 3 let *any* group pass through as its
    own capability.
    """
    capabilities: list[str] = []
    for raw_group in groups:
        if not isinstance(raw_group, str) or not raw_group:
            continue
        group = (aliases or {}).get(raw_group, raw_group)
        if group in ORGANISATION_BUNDLES:
            capabilities.extend(ROLE_BUNDLES[group])
        elif group in ORGANISATION_PERMISSIONS:
            capabilities.append(group)
    return _ordered_unique(capabilities)
