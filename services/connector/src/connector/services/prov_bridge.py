"""Maps connector events to PROV-O domain events and emits them."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ds_auth import Principal

from ..clients.provenance import ProvenanceClient

log = logging.getLogger(__name__)


def acting_principal(
    principal: "Principal | None", *, on_behalf_of: str | None = None
) -> dict | None:
    """Render a verified caller as the `acted_by` block of a provenance event.

    Built from the **verified** `Principal` — never from a header or a body field —
    so the record cannot be authored by the party it names.

    Deliberately narrow: the opaque `sub`, the issuer that gives it meaning, whether
    it was a machine, and the owner the caller claimed to act for. No email, no
    username, no display name. The rest of the provenance model keeps to codes,
    pseudonymous identifiers and hashes, and an audit trail is not a reason to start
    storing people's names.
    """
    if principal is None:
        return None
    if not principal.subject:
        # The token authenticated and authorised, and identifies nobody. In
        # Keycloak this means the client is missing the `basic` client scope, which
        # is what puts `sub` in an *access* token — so the act is recorded as having
        # been performed by "". Loud, because a blank attribution is worse than an
        # absent one: it looks answered.
        log.error(
            "provenance attribution has no subject — the token carries no `sub`. "
            "Add the `basic` client scope to the login client; until then this act "
            "is unattributable."
        )
    issuer = principal.claims.get("iss") if isinstance(principal.claims, dict) else None
    return {
        "subject": principal.subject,
        "issuer": issuer if isinstance(issuer, str) else None,
        "on_behalf_of": on_behalf_of,
        "is_service": principal.is_service,
    }



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _did(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("did:"):
        return value
    return f"did:web:{value}"


class ProvBridge:
    def __init__(self, client: ProvenanceClient, participant_id: str):
        self._prov = client
        self._participant_id = participant_id

    async def catalogue_published(
        self,
        data_product_id: str,
        title: str | None = None,
        description: str | None = None,
        event_id: str | None = None,
        acted_by: dict | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "CataloguePublished",
            "event_id": event_id,
            "occurred_at": _now(),
            "data_product_id": data_product_id,
            "provider_did": _did(self._participant_id),
            "title": title,
            "description": description,
            "acted_by": acted_by,
        })

    async def catalog_viewed(
        self,
        provider_id: str,
        consumer_id: str | None = None,
        user_id: str | None = None,
        counter_party_address: str | None = None,
        dataset_count: int | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "CatalogViewed",
            "event_id": event_id,
            "occurred_at": _now(),
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
            "counter_party_address": counter_party_address,
            "dataset_count": dataset_count,
        })

    async def access_requested(
        self,
        request_id: str,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        user_id: str,
        purpose: list[str] | None = None,
        offer_id: str | None = None,
        event_id: str | None = None,
        declared_purpose: list[str] | None = None,
        declared_from: datetime | None = None,
        declared_until: datetime | None = None,
        justification_ref: str | None = None,
    ) -> None:
        """``purpose`` is what the offer permits; ``declared_purpose`` is what
        the consumer said it wanted. Keeping them apart is the point: collapsing
        them would make an offer's permissions look like a consumer's statement.

        Every field here stays codes, IRIs and references — ``justification_ref``
        is an opaque external id, never the justification text itself.
        """
        await self._prov.emit_event({
            "event_type": "AccessRequested",
            "event_id": event_id or f"access-request:{request_id}",
            "occurred_at": _now(),
            "request_id": request_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
            "purpose": purpose or [],
            "offer_id": offer_id,
            "declared_purpose": declared_purpose or [],
            "declared_from": declared_from.isoformat() if declared_from else None,
            "declared_until": declared_until.isoformat() if declared_until else None,
            "justification_ref": justification_ref,
        })

    async def negotiation_started(
        self,
        negotiation_id: str,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        user_id: str | None = None,
        offer_id: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "NegotiationStarted",
            "event_id": event_id or f"negotiation-started:{negotiation_id}",
            "occurred_at": _now(),
            "negotiation_id": negotiation_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
            "offer_id": offer_id,
        })

    async def negotiation_finalized(
        self,
        negotiation_id: str,
        agreement_id: str,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        user_id: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "NegotiationFinalized",
            "event_id": event_id or f"negotiation-finalized:{negotiation_id}",
            "occurred_at": _now(),
            "negotiation_id": negotiation_id,
            "agreement_id": agreement_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
        })

    async def negotiation_terminated(
        self,
        negotiation_id: str,
        data_product_id: str | None = None,
        provider_id: str | None = None,
        consumer_id: str | None = None,
        user_id: str | None = None,
        reason: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "NegotiationTerminated",
            "event_id": event_id or f"negotiation-terminated:{negotiation_id}",
            "occurred_at": _now(),
            "negotiation_id": negotiation_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
            "reason": reason,
        })

    async def contract_agreement_signed(
        self,
        agreement_id: str,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        policy_hash: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "ContractAgreementSigned",
            "event_id": event_id or agreement_id,
            "occurred_at": _now(),
            "agreement_id": agreement_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "policy_hash": policy_hash,
        })

    async def transfer_started(
        self,
        transfer_id: str,
        agreement_id: str,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        user_id: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "TransferStarted",
            "event_id": event_id or f"transfer-started:{transfer_id}",
            "occurred_at": _now(),
            "transfer_id": transfer_id,
            "agreement_id": agreement_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
        })

    async def data_transfer_completed(
        self,
        transfer_id: str,
        agreement_id: str,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        bytes_transferred: int | None = None,
        derived_dataset_iri: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "DataTransferCompleted",
            "event_id": event_id or transfer_id,
            "occurred_at": _now(),
            "transfer_id": transfer_id,
            "agreement_id": agreement_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "bytes_transferred": bytes_transferred,
            "derived_dataset_iri": derived_dataset_iri,
        })

    async def query_executed(
        self,
        data_product_id: str,
        provider_id: str | None = None,
        consumer_id: str | None = None,
        user_id: str | None = None,
        subject_id: str | None = None,
        agreement_id: str | None = None,
        transfer_id: str | None = None,
        row_count: int | None = None,
        authorized_subject_ids: list[str] | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "QueryExecuted",
            "event_id": event_id,
            "occurred_at": _now(),
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "user_did": _did(user_id),
            "subject_id": subject_id,
            "agreement_id": agreement_id,
            "transfer_id": transfer_id,
            "row_count": row_count,
            "authorized_subject_ids": authorized_subject_ids,
        })

    async def access_revoked(
        self,
        data_product_id: str,
        provider_id: str,
        consumer_id: str,
        subject_id: str,
        agreement_id: str | None = None,
        transfer_id: str | None = None,
        reason: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "AccessRevoked",
            "event_id": event_id,
            "occurred_at": _now(),
            "agreement_id": agreement_id,
            "transfer_id": transfer_id,
            "data_product_id": data_product_id,
            "provider_did": _did(provider_id),
            "consumer_did": _did(consumer_id),
            "subject_id": subject_id,
            "reason": reason,
        })

    # ── Consent & disclosure (Block C) ────────────────────────────────────────
    #
    # These carry codes, DIDs and hashes only, never PII. ``consumer_id`` may be
    # the scoped wildcard "*"; it is passed through verbatim rather than through
    # ``_did`` so the provenance record keeps the same token the consent row holds.

    async def consent_granted(
        self,
        subject_id: str,
        dataset_id: str,
        consumer_id: str | None = None,
        offer_id: str | None = None,
        purpose: list[str] | None = None,
        controller: str | None = None,
        controller_role: str | None = None,
        legal_basis: dict | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "ConsentGranted",
            "event_id": event_id,
            "occurred_at": _now(),
            "subject_id": _did(subject_id),
            "dataset_id": dataset_id,
            "consumer_did": consumer_id,
            "offer_id": offer_id,
            "purpose": purpose or [],
            "controller": controller,
            "controller_role": controller_role,
            "legal_basis": legal_basis,
        })

    async def consent_revoked(
        self,
        subject_id: str,
        dataset_id: str,
        consumer_id: str | None = None,
        offer_id: str | None = None,
        purpose: list[str] | None = None,
        controller: str | None = None,
        controller_role: str | None = None,
        reason: str | None = None,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "ConsentRevoked",
            "event_id": event_id,
            "occurred_at": _now(),
            "subject_id": _did(subject_id),
            "dataset_id": dataset_id,
            "consumer_did": consumer_id,
            "offer_id": offer_id,
            "purpose": purpose or [],
            "controller": controller,
            "controller_role": controller_role,
            "reason": reason,
        })

    async def data_ingested(
        self,
        dataset_id: str,
        provider_id: str | None = None,
        source_ref: str | None = None,
        record_count: int | None = None,
        consent_snapshot_hash: str | None = None,
        agreement_ref: str | None = None,
        event_id: str | None = None,
        acted_by: dict | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "DataIngested",
            "event_id": event_id,
            "occurred_at": _now(),
            "dataset_id": dataset_id,
            "provider_did": _did(provider_id),
            "source_ref": source_ref,
            "record_count": record_count,
            "consent_snapshot_hash": consent_snapshot_hash,
            "agreement_ref": agreement_ref,
            "acted_by": acted_by,
        })

    # `DataDisclosed` and `UsageObligationFulfilled` had a method here and no
    # caller, which read as coverage this bridge does not have. Two different
    # reasons, and the difference is the point:
    #
    # - **`DataDisclosed` is emitted, but not from here.** Its producer is the
    #   out-of-repo onboarding service after a CSV export, which holds
    #   `provenance.write` (`services/keycloak/clients.yaml`) and posts to
    #   `POST /prov/events` itself. A Python method on this class was never
    #   reachable by it. Deleting the method drops no emission.
    # - **`UsageObligationFulfilled` is emitted by nobody, anywhere.** That is a
    #   real gap against rulebook `L-1`/`L-15`, and it is recorded as one in
    #   `docs/rulebook/provenance-and-logging.md` rather than left looking
    #   covered. The event is a *consumer reporting* an obligation it met, so
    #   closing it needs an inbound route with a guard — not a bridge method.
    #
    # `tests/test_provenance_events.py` asserts this class carries an emitter for
    # every event type the connector produces, and only those.
