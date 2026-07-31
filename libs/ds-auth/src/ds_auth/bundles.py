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
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping

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
    "ds-participant-admin": (
        "connector.provider.read",
        "connector.provider.write",
        "connector.history.read",
        "connector.registry.invalidate",
        "connector.consent.provision",
        "connector.ingestion.record",
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

    Layer B maps a *foreign* IdP's group names onto ds bundles::

        {"celine-manager": "ds-participant-admin", "celine-viewer": "ds-participant-viewer"}

    The values must be **bundle names**, never capabilities. An alias pointing
    straight at ``connector.provider.write`` would make deployment configuration a
    permission table, which is the thing Layer A exists to prevent — so an unknown
    target is dropped and named in the log rather than honoured. Dropping is the
    safe direction: the group then falls through to pass-through and grants only
    itself, which matches nothing.

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
            "Expected {\"foreign-group\": \"ds-bundle\"}.",
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
            logger.error("ds-auth: ignoring non-string alias entry %r -> %r", foreign, target)
            continue
        if target not in ROLE_BUNDLES:
            logger.error(
                "ds-auth: ignoring alias %r -> %r: %r is not a role bundle. An alias "
                "may only name a bundle (%s), never a capability — otherwise the "
                "permission table becomes deployment configuration.",
                foreign,
                target,
                target,
                ", ".join(sorted(ROLE_BUNDLES)),
            )
            continue
        aliases[foreign] = target

    if aliases:
        logger.info(
            "ds-auth: group alias map active — %s",
            ", ".join(f"{k} -> {v}" for k, v in sorted(aliases.items())),
        )
    return aliases


def expand_bundles(
    groups: Iterable[str], aliases: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """Expand bundle names into capabilities, preserving order and deduping.

    Four rules, in order:

    0. A **Layer B alias** is translated first: a foreign IdP's group name becomes
       the ds bundle a deployment mapped it to. Aliases are validated at parse time
       (:func:`parse_group_aliases`) so they can only name bundles, never
       capabilities — the permission table stays in Layer A, in code.
    1. A known bundle name expands to its capability set.
    2. A **machine-identity** permission is dropped. It is not grantable to a
       human however the group is named — a realm that defines a group called
       ``connector.internal`` must not thereby hand out the connector's own
       identity. This is checked **after** aliasing, so an alias cannot smuggle one
       in either.
    3. Anything else passes through **verbatim**, as its own capability.

    Rule 3 is what makes the migration free: a realm still carrying the old
    scope-named groups keeps authorizing exactly as it does today, so bundles can
    be introduced additively and the mirror deleted once nothing depends on it.
    It is also why an unrecognised group is harmless rather than an error — it
    grants precisely itself, which matches nothing unless a call site asks for
    that name.
    """
    result: list[str] = []
    seen: set[str] = set()

    def add(permission: str) -> None:
        if permission and permission not in seen:
            seen.add(permission)
            result.append(permission)

    for raw_group in groups:
        if not isinstance(raw_group, str) or not raw_group:
            continue
        # Rule 0: translate a foreign name before anything else looks at it.
        group = (aliases or {}).get(raw_group, raw_group)
        capabilities = ROLE_BUNDLES.get(group)
        if capabilities is not None:
            for capability in capabilities:
                add(capability)
        elif group in MACHINE_IDENTITY_PERMISSIONS:
            continue
        else:
            add(group)

    return tuple(result)
