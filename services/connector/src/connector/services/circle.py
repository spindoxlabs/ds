"""The circle — who is covered by an existing consent, and who must be asked.

    in_circle(participant) := has a current accepted agreement
                           AND satisfies offer.recipients.processors.admitted_by

The distinction this module draws is the consent boundary:

- A **processor** of the offer's controller acts on its instructions under a
  DPA (GDPR Art. 28).  The controller has not changed and neither has the
  processing operation, so the party is *disclosed and notified*, never asked.
- An **independent controller** decides its own purposes.  Consent under
  Art. 4(11) is consent to a specific controller's processing, so a new one is
  a legitimate new question — delivered non-blocking via ``POST /consent/request``.

The system cannot infer capacity; the agreement must declare it.  Until the
identity-registry carries agreements with a ``capacity`` field, capacity is
unprovable here — and unprovable resolves to "outside the circle", which asks
rather than assumes.  That is the safe direction: a redundant question is
recoverable, a skipped one is not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

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
    value: str,
    requester_did: str,
    identity_registry_url: str,
    token_provider=None,
) -> bool:
    if kind == "membership":
        return await _is_member(identity_registry_url, requester_did, value, token_provider)
    if kind == "credential_type":
        return await _holds_credential(
            identity_registry_url, requester_did, value, token_provider
        )
    # An unknown constraint kind cannot be evaluated, so it cannot be satisfied.
    log.warning(
        "Unknown admitted_by constraint '%s' — treating as unsatisfied", kind
    )
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
    """
    try:
        async with httpx.AsyncClient(
            base_url=identity_registry_url.rstrip("/"), timeout=10.0
        ) as client:
            resp = await client.get(
                "/admin/credentials",
                params={"subject_did": subject_did, "type": credential_type},
                headers=await _headers(token_provider),
            )
            if resp.status_code != 200:
                return False
            body = resp.json()
            items = body if isinstance(body, list) else body.get("items") or []
            return any(
                not item.get("revoked", False)
                for item in items
                if isinstance(item, dict)
            )
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
            return capacity if capacity in {
                PROCESSOR, JOINT_CONTROLLER, INDEPENDENT_CONTROLLER
            } else None
    except httpx.HTTPError:
        # The agreements surface lands with organisation onboarding; until then
        # every requester is treated as outside the circle.
        log.debug("Agreements endpoint unavailable — treating %s as outside", participant_did)
        return None
