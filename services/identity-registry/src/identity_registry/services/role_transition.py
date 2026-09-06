"""A role change is a reissue.

A verifiable credential cannot be edited. VCDM 2.0 defines no property,
algorithm or section that changes one after issuance, and §5.4 says a refresh
means obtaining a *new* credential — so when what a credential claims about
somebody stops being true, the model's answer is to retire the old one and
issue its successor. See `docs/standards/vcdm-2.0.md`.

That is why there is no `PATCH`. The missing verb is not an oversight in this
API; it is the model refusing a shape it does not have.

**Retired means suspended, not revoked.** The two are different answers and a
verifier can tell them apart (`P-25`): revocation says the attestation was
withdrawn and is terminal, suspension says it does not currently hold. A
superseded credential was not withdrawn — it was replaced, and the person may
hold a successor the same second. Writing a revocation bit would tell every
counterparty something the issuer does not mean.

**Both halves, one transaction.** The failure mode of doing them separately is
a person holding two credentials making different claims about themselves, or
none at all. Delivery to the custodian is deliberately *outside* it — it is a
call to somebody else's service and it fails independently, exactly as it does
for a first issuance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Credential
from .crypto import decrypt_private_jwk, generate_credential_id, require_private_jwk
from .issuance import active_data_subject_credential
from .org_onboarding import suspension_index
from .status_list import (
    SUSPENSION_LIST_ID,
    allocate_suspendable_index,
    suspend_status_list_index,
)
from .vc import build_data_subject_credential, sign_credential

log = logging.getLogger(__name__)


class RoleTransitionError(Exception):
    """The transition cannot be performed, and nothing has been written."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Transition:
    """What the transition did, both halves named.

    The superseded credential is named because a caller that only learns the new
    id cannot tell a transition from a first issuance, and the two have
    different consequences for anything holding the old one.
    """

    subject_did: str
    superseded_credential_id: str
    credential_id: str
    signed_vc: dict
    from_role: str | None
    to_role: str


def community_role(credential_json: dict | None) -> str | None:
    """The community role a credential claims, or `None`."""
    subject = (credential_json or {}).get("credentialSubject") or {}
    value = subject.get("communityRole")
    return value if isinstance(value, str) else None


async def transition_community_role(
    db: AsyncSession,
    settings: Settings,
    *,
    subject_did: str,
    vc_role: str | None,
    to_role: str,
    trust_anchor_did: str,
    trust_anchor_key,
    linked_participant_did: str | None = None,
    allowed_actions: list[str] | None = None,
    ttl_days: int | None = None,
    verified_by: str | None = None,
    verification_method: str | None = None,
) -> Transition:
    """Suspend the superseded credential and issue its successor.

    `vc_role` selects *which* credential is being superseded — a person holds
    one per protocol role (`DataSubject`, `ConsumerUser`), and a role change
    concerns one of them, not all of them.
    """
    predecessor = await active_data_subject_credential(db, subject_did, vc_role)
    if predecessor is None:
        raise RoleTransitionError(
            f"{subject_did} holds no active DataSubjectCredential with "
            f"role={vc_role or '-'}, so there is nothing to supersede. Issue one "
            "first: a transition changes a claim, it does not create the holder.",
            status_code=404,
        )

    from_role = community_role(predecessor.credential_json)
    if from_role == to_role:
        raise RoleTransitionError(
            f"{subject_did} already holds communityRole={to_role!r}. A reissue "
            "would burn a status-list index and suspend a credential to replace "
            "it with an identical one.",
            status_code=409,
        )

    # **Refused, not worked around.** A predecessor naming no suspension
    # register can only be revoked, and revoking it would assert the attestation
    # was withdrawn. Every credential issued since `P-27` names both registers;
    # one issued before it must be reissued before its holder is transitionable.
    index = suspension_index(predecessor.credential_json)
    if index is None:
        raise RoleTransitionError(
            f"Credential {predecessor.id} names no suspension register, so no "
            "verifier would see it superseded. It predates `P-27`; reissue it "
            "before changing this person's role.",
            status_code=409,
        )

    ttl = min(
        ttl_days or settings.default_credential_ttl_days,
        settings.max_credential_ttl_days,
    )

    # The successor carries the predecessor's claims unless the caller replaces
    # them. A transition changes the community role; it is not an opportunity to
    # silently drop everything else the credential said.
    prior_subject = (predecessor.credential_json or {}).get("credentialSubject") or {}
    linked = linked_participant_did or prior_subject.get("linkedParticipant")
    actions = allowed_actions or prior_subject.get("allowedActions")

    successor_id = generate_credential_id()
    sl_index = await allocate_suspendable_index(db)
    vc = build_data_subject_credential(
        issuer_did=trust_anchor_did,
        subject_did=subject_did,
        role=vc_role,
        community_role=to_role,
        linked_participant_did=linked,
        allowed_actions=actions,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=settings.status_list_url(),
        suspension_list_credential_url=settings.status_list_url(SUSPENSION_LIST_ID),
        status_list_index=sl_index,
        credential_id=successor_id,
        ttl_days=ttl,
        # Who established the fact behind the change, and how (`D-53`).
        # Commissioning a meter is something the energy community establishes,
        # not the dataspace, and the attestation travels with the credential
        # exactly as it does for a first issuance.
        verified_by=verified_by or prior_subject.get("verifiedBy"),
        verification_method=verification_method
        or prior_subject.get("verificationMethod"),
    )
    raw_jwk = decrypt_private_jwk(
        require_private_jwk(
            trust_anchor_key.private_jwk,
            kid=trust_anchor_key.kid,
            purpose="sign as the trust anchor",
        ),
        settings.encryption_key,
    )
    signed_vc = sign_credential(vc, raw_jwk, trust_anchor_key.kid)

    now = datetime.now(UTC)
    db.add(
        Credential(
            id=successor_id,
            credential_type="DataSubjectCredential",
            issuer_did=trust_anchor_did,
            subject_did=subject_did,
            credential_json=signed_vc,
            status_list_index=sl_index,
            expires_at=now + timedelta(days=ttl),
        )
    )

    # The suspension, in the same transaction as the issuance. Neither order is
    # safe on its own: suspending first leaves the person with nothing if
    # signing fails, issuing first leaves two live credentials disagreeing.
    await suspend_status_list_index(db, index)
    predecessor.status = "suspended"

    await db.flush()
    log.info(
        "community role %s -> %s for %s: %s superseded by %s",
        from_role or "-",
        to_role,
        subject_did,
        predecessor.id,
        successor_id,
    )
    return Transition(
        subject_did=subject_did,
        superseded_credential_id=predecessor.id,
        credential_id=successor_id,
        signed_vc=signed_vc,
        from_role=from_role,
        to_role=to_role,
    )


__all__ = [
    "RoleTransitionError",
    "Transition",
    "community_role",
    "transition_community_role",
]
