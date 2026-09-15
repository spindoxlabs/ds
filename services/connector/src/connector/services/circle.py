"""The circle — who is covered by an existing consent, and who must be asked.

    in_circle(participant) := has a current accepted agreement
                           AND satisfies offer.recipients.processors.admitted_by

The distinction this module draws is the consent boundary:

- A **processor** of the offer's controller acts on its instructions under a
  DPA (GDPR Art. 28).  The controller has not changed and neither has the
  processing operation, so the party is *disclosed and notified*, never asked.
- An **independent controller** decides its own purposes.  Consent under
  Art. 4(11) is consent to a specific controller's processing, so a new one is
  a legitimate new question.

Where that question comes from is **not** ``POST /consent/request``, which this
header used to name.  That was a cross-participant push channel and it is gone
(rulebook §5, `D-16`): a consumer now simply negotiates, ``ConsentPendingGuard``
parks the negotiation, and the ask is recorded against EDC's DCP-verified
``counterPartyId``.  The route survives only as **provider-local** seeding for an
operator or the portal, authenticated as a service.  The distinction matters for
anyone reading this module to find out how a question reaches a person: nothing
here delivers one, and this module's verdict is consumed by the pending guard —
``/internal/consent/check`` answers ``should_ask`` from it (`D-5`, `D-18`).

The system cannot infer capacity; the agreement must declare it.  Until the
identity-registry carries agreements with a ``capacity`` field, capacity is
unprovable here — and unprovable resolves to "outside the circle", which asks
rather than assumes.  That is the safe direction: a redundant question is
recoverable, a skipped one is not.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from ds.governance.sharing import SharingOffer

log = logging.getLogger(__name__)

PROCESSOR = "processor"
JOINT_CONTROLLER = "joint_controller"
INDEPENDENT_CONTROLLER = "independent_controller"


@dataclass(frozen=True)
class CircleVerdict:
    """Why a requester is or is not covered by an existing consent."""

    inside: bool
    capacity: str | None
    reason: str

    @property
    def covered_processor(self) -> bool:
        """Covered by disclosure — asking again would be wrong, not merely redundant."""
        return self.inside and self.capacity == PROCESSOR


async def evaluate(
    offer: SharingOffer,
    requester_did: str,
    identity_registry_url: str,
    token_provider=None,
) -> CircleVerdict:
    """Decide whether *requester_did* is inside the circle of *offer*.

    Both halves of the definition are checked against the identity-registry, so
    the wildcard in a standing consent means "anyone the controller has a signed
    agreement with, for this purpose" rather than "anyone governance admits".
    """
    if not identity_registry_url:
        return CircleVerdict(False, None, "no identity-registry configured")

    capacity = await _agreement_capacity(
        identity_registry_url, requester_did, token_provider
    )
    if capacity is None:
        return CircleVerdict(
            False, None, "no current accepted agreement declares a capacity"
        )

    admitted, detail = await _satisfies_admitted_by(
        offer, requester_did, identity_registry_url, token_provider
    )
    if not admitted:
        return CircleVerdict(False, capacity, detail)

    return CircleVerdict(True, capacity, f"admitted as {capacity}")


async def admits_wildcard(
    offer: SharingOffer,
    requester_did: str,
    identity_registry_url: str,
    owners_registry=None,
    token_provider=None,
    cache: dict | None = None,
    cache_ttl: float = 0.0,
) -> tuple[bool, str]:
    """Does *offer*'s wildcard grant admit *requester_did*?  (`D-14`)

    A person who consents to an offer rather than to a named counterparty gets a
    ``consumer_id = "*"`` row.  D-14 says what that row means: it "admits any
    party **inside the circle** for that controller and purpose", and "never
    admits a new controller".  Two parties qualify, and no others:

    - **the offer's controller** — the party the person was actually told about,
      and whose processing they consented to;
    - **a processor of that controller**, inside the circle, disclosed under
      Art. 13(1)(e) rather than asked.

    Everyone else is *not consented*, including a joint controller that satisfies
    ``admitted_by``: EDPB 05/2020 para 65 asks that controllers relying on the
    original consent "should all be named", and being inside the circle is not
    being named.  That matches :attr:`CircleVerdict.covered_processor`, which is
    ``inside and capacity == PROCESSOR`` — this function is the same boundary
    applied on the path where consent is *present*, which is the path that never
    consulted it.

    The remedy for a refusal is not a closed door: the guard parks, the person is
    asked, and a per-party grant (`D-15`) admits them.

    **The controller is an alias and the requester is a DID**, so the comparison
    goes through the owner registry — `example-org` and
    ``did:web:rec.dataspaces.localhost`` are the same organisation and compare
    unequal as strings.  Without a registry the alias cannot be resolved, and an
    unresolvable controller resolves to *not admitted*: the same safe direction
    the rest of this module takes, because a redundant question is recoverable
    and a skipped one is not.
    """
    controller_alias = offer.recipients.controller
    cached = _admission_cached(cache, offer.id, requester_did, cache_ttl)
    if cached is not None:
        return cached

    # An unresolvable controller disables **this branch only**. Whether the
    # requester is a processor is independent evidence — it comes from what that
    # organisation signed and from the offer's own `admitted_by` — so returning
    # early here would deny a covered processor for a reason that has nothing to
    # do with it, and `D-5` says a processor is disclosed rather than asked.
    controller_did = await _controller_did(controller_alias, owners_registry)

    if controller_did is not None and requester_did == controller_did:
        return _admission_remember(
            cache,
            offer.id,
            requester_did,
            cache_ttl,
            (True, f"the offer's controller ({controller_alias})"),
        )

    verdict = await evaluate(
        offer,
        requester_did=requester_did,
        identity_registry_url=identity_registry_url,
        token_provider=token_provider,
    )
    if verdict.covered_processor:
        return _admission_remember(
            cache,
            offer.id,
            requester_did,
            cache_ttl,
            (True, f"a processor inside the circle of {controller_alias}"),
        )
    return _admission_remember(
        cache,
        offer.id,
        requester_did,
        cache_ttl,
        (False, f"not the controller and not its processor: {verdict.reason}"),
    )


async def _controller_did(alias: str, owners_registry) -> str | None:
    """The DID behind an owner alias, or ``None`` when it cannot be resolved."""
    if owners_registry is None:
        log.warning(
            "No owners registry: controller alias %r cannot be resolved to a DID, "
            "so the wildcard admits nobody by the controller branch",
            alias,
        )
        return None
    try:
        entry = await owners_registry.by_id(alias)
    except Exception as exc:  # noqa: BLE001 — a registry blip must not admit
        log.error("Owner lookup failed for controller %r: %s", alias, exc)
        return None
    return getattr(entry, "did", None) if entry is not None else None


# Admission is read once per dataset per decision, and the circle costs two
# identity-registry round trips. Cached on the **same clock as the decision it
# belongs to** (`dataplane_decision_ttl`, 30 s) rather than a clock of its own:
# `dataset-api` honours that TTL as `cache.ttl_seconds`, so a longer one here
# would let a data plane keep serving an allow after admission narrowed, and a
# shorter one would buy nothing the decision cache does not already give away.
#
# **The store belongs to the caller, not to this module.** It was a module-level
# dict, which is one process-wide cache shared by every app built in that
# process — verdicts leaked between apps, and the suite caught it immediately:
# a test passed alone and failed in the suite because an earlier test's
# admission was still cached. `request.app.state` is the same lifetime as the
# registries this function already reads, and it is thrown away with the app.


def _admission_cached(
    cache: dict | None, offer_id: str, requester_did: str, ttl: float
) -> tuple[bool, str] | None:
    if cache is None or ttl <= 0:
        return None
    hit = cache.get((offer_id, requester_did))
    if hit is None or (time.monotonic() - hit[0]) >= ttl:
        return None
    return hit[1]


def _admission_remember(
    cache: dict | None,
    offer_id: str,
    requester_did: str,
    ttl: float,
    answer: tuple[bool, str],
) -> tuple[bool, str]:
    if cache is not None and ttl > 0:
        cache[(offer_id, requester_did)] = (time.monotonic(), answer)
    return answer


async def is_covered_processor(
    offers,
    requester_did: str,
    identity_registry_url: str,
    token_provider=None,
) -> bool:
    """Is *requester_did* disclosed rather than asked, across all these offers?

    Every offer that bundles this dataset and purpose must cover the requester
    as a processor before the question is suppressed.  Coverage by one offer and
    not another means there is a controller whose processing the person has not
    been asked about, and that question still has to be put.

    An empty offer list is *not* coverage.  It means no consent-based offer was
    found for the pair, so nothing has been established about the requester's
    capacity — and this module's whole doctrine is that unprovable resolves to
    outside the circle, because a redundant question is recoverable and a
    skipped one is not.
    """
    if not offers:
        return False
    for offer in offers:
        verdict = await evaluate(
            offer,
            requester_did=requester_did,
            identity_registry_url=identity_registry_url,
            token_provider=token_provider,
        )
        if not verdict.covered_processor:
            log.debug(
                "Requester %s not covered by offer %s: %s",
                requester_did,
                offer.id,
                verdict.reason,
            )
            return False
    return True


async def _satisfies_admitted_by(
    offer: SharingOffer,
    requester_did: str,
    identity_registry_url: str,
    token_provider=None,
) -> tuple[bool, str]:
    """Every ``admitted_by`` constraint must hold — they are ANDed, not ORed.

    A category with no constraints admits nobody.  The compliance gate warns
    about that shape precisely because an unconstrained category is a promise
    the platform cannot check.
    """
    constraints = offer.recipients.processors.admitted_by
    if not constraints:
        return False, "processor category declares no admitted_by constraints"

    for constraint in constraints:
        for kind, value in constraint.items():
            ok = await _check_constraint(
                kind, value, requester_did, identity_registry_url, token_provider
            )
            if not ok:
                return False, f"failed admitted_by constraint {kind}={value}"
    return True, "all admitted_by constraints satisfied"


async def _check_constraint(
    kind: str,
    value: Any,
    requester_did: str,
    identity_registry_url: str,
    token_provider=None,
) -> bool:
    if kind == "membership":
        return await _is_member(
            identity_registry_url, requester_did, value, token_provider
        )
    if kind == "credential_type":
        return await _holds_credential(
            identity_registry_url, requester_did, value, token_provider
        )
    if kind == "credential_claim":
        return await _holds_credential_claim(
            identity_registry_url, requester_did, value, token_provider
        )
    # An unknown constraint kind cannot be evaluated, so it cannot be satisfied.
    log.warning("Unknown admitted_by constraint '%s' — treating as unsatisfied", kind)
    return False


async def _holds_credential_claim(
    identity_registry_url: str,
    subject_did: str,
    spec: Any,
    token_provider=None,
) -> bool:
    """Whether *subject_did* holds a credential asserting a particular claim.

    ``admitted_by: [{credential_claim: {type: DataSubjectCredential, claim:
    communityRole, value: prosumer}}]`` — an offer restricted to prosumers.

    `credential_type` cannot express this. A community role is a *claim* on a
    person's `DataSubjectCredential`, not a credential type of its own, so that
    one person keeps one credential per protocol role rather than accumulating
    one per role they have ever held. The kinds are siblings: one asks what
    somebody holds, the other what it says.

    A malformed spec is **unsatisfied, not an error**, for the same reason an
    unknown kind is: a constraint this connector cannot evaluate must not admit
    anyone. It is logged, because silently admitting nobody is the failure that
    looks like a working deny.
    """
    if not isinstance(spec, dict):
        log.warning(
            "admitted_by credential_claim expects a mapping with type/claim/value, "
            "got %r — treating as unsatisfied",
            spec,
        )
        return False
    credential_type = spec.get("type") or "DataSubjectCredential"
    claim = spec.get("claim")
    value = spec.get("value")
    if not claim or value is None:
        log.warning(
            "admitted_by credential_claim needs both 'claim' and 'value' (got %r) "
            "— treating as unsatisfied",
            spec,
        )
        return False
    try:
        async with httpx.AsyncClient(
            base_url=identity_registry_url.rstrip("/"), timeout=10.0
        ) as client:
            resp = await client.get(
                "/credentials/check",
                params={
                    "subject_did": subject_did,
                    "type": credential_type,
                    "claim": claim,
                    "value": value,
                },
                headers=await _headers(token_provider),
            )
            if resp.status_code != 200:
                log.warning(
                    "Claim check for %s (%s=%s) answered %s — not admitted",
                    subject_did,
                    claim,
                    value,
                    resp.status_code,
                )
                return False
            return bool(resp.json().get("holds", False))
    except httpx.HTTPError as exc:
        log.error("Claim check failed for %s: %s", subject_did, exc)
        return False


async def _headers(token_provider) -> dict[str, str]:
    if token_provider:
        return {"Authorization": f"Bearer {await token_provider()}"}
    return {}


async def _is_member(
    identity_registry_url: str,
    user_did: str,
    organization_alias: str,
    token_provider=None,
) -> bool:
    try:
        async with httpx.AsyncClient(
            base_url=identity_registry_url.rstrip("/"), timeout=10.0
        ) as client:
            resp = await client.get(
                "/memberships/check",
                params={"user_did": user_did, "organization": organization_alias},
                headers=await _headers(token_provider),
            )
            if resp.status_code == 200:
                return bool(resp.json().get("member", False))
            return False
    except httpx.HTTPError as exc:
        log.error("Membership check failed for %s: %s", user_did, exc)
        return False


async def _holds_credential(
    identity_registry_url: str,
    subject_did: str,
    credential_type: str,
    token_provider=None,
) -> bool:
    """Whether *subject_did* holds a valid credential of *credential_type*.

    Returns False when the registry cannot answer — an unverifiable credential
    claim must not admit anyone.

    Asks `GET /credentials/check`, the sibling of the `/memberships/check` above.
    It used to ask `GET /admin/credentials` and decide validity itself, which was
    wrong three times over and is worth recording because two of the three fail
    *open*:

    1. that route requires `identity-registry.admin`, which this client does not
       hold and `clients.yaml` refuses a service client — so every check 403'd;
    2. it ignores the `type` parameter, so the answer covered every credential
       the subject holds, of any type;
    3. its `CredentialSummary` has a `status`, never a `revoked` field, so
       `item.get("revoked", False)` was `False` for every entry and the `any()`
       was satisfied by the mere existence of one.

    Widening the grant would therefore have turned an always-negative check into
    an always-positive one. Validity is now decided where the state lives.
    """
    try:
        async with httpx.AsyncClient(
            base_url=identity_registry_url.rstrip("/"), timeout=10.0
        ) as client:
            resp = await client.get(
                "/credentials/check",
                params={"subject_did": subject_did, "type": credential_type},
                headers=await _headers(token_provider),
            )
            if resp.status_code != 200:
                log.warning(
                    "Credential check for %s (%s) answered %s — not admitted",
                    subject_did,
                    credential_type,
                    resp.status_code,
                )
                return False
            return bool(resp.json().get("holds", False))
    except httpx.HTTPError as exc:
        log.error("Credential check failed for %s: %s", subject_did, exc)
        return False


async def _agreement_capacity(
    identity_registry_url: str,
    participant_did: str,
    token_provider=None,
) -> str | None:
    """Capacity declared by the participant's current accepted agreement.

    Returns None when no agreement exists, none is current, or the registry does
    not yet expose agreements — all of which mean "not provably inside".
    """
    try:
        async with httpx.AsyncClient(
            base_url=identity_registry_url.rstrip("/"), timeout=10.0
        ) as client:
            resp = await client.get(
                "/agreements/current",
                params={"participant_did": participant_did},
                headers=await _headers(token_provider),
            )
            if resp.status_code != 200:
                return None
            capacity = resp.json().get("capacity")
            return (
                capacity
                if capacity in {PROCESSOR, JOINT_CONTROLLER, INDEPENDENT_CONTROLLER}
                else None
            )
    except httpx.HTTPError:
        # The agreements surface lands with organisation onboarding; until then
        # every requester is treated as outside the circle.
        log.debug(
            "Agreements endpoint unavailable — treating %s as outside", participant_did
        )
        return None
