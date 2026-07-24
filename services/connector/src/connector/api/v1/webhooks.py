"""EDC webhook receivers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ConsumerAccessRequestORM
from ...dependencies import get_db, get_settings_dep, require_webhook_scope
from ...schemas.webhooks import ContractNegotiationEvent, TransferProcessEvent
from ...services.agreement_service import terminate_agreement, upsert_agreement

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# How a negotiation state maps onto the consumer-side access-request record.
# Only states that settle something are listed: a request sitting in
# `negotiating` already says what REQUESTED or OFFERED would say. The values
# match the vocabulary `GET /consumer/requests` polls into place, so an event
# and a poll cannot disagree about the same negotiation.
_ACCESS_REQUEST_STATUS = {
    "TERMINATED": "terminated",
    "FINALIZED": "finalized",
}

# The consumer's own decision outranks anything the negotiation reports: a
# request the user revoked must not be resurrected as `finalized` by a
# FINALIZED event still in flight, and a transfer already under way is further
# along than the negotiation state can express.
_ACCESS_REQUEST_SETTLED = {"revoked", "transferring", "transferred"}


@router.post("/transfer-process", status_code=200)
async def transfer_process_event(
    event: TransferProcessEvent,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_webhook_scope),
):
    event_type = event.type
    log.info("Transfer-process webhook: %s transfer=%s", event_type, event.transfer_id)

    if "COMPLETED" in event_type or "STARTED" in event_type:
        prov = request.app.state.prov
        await prov.data_transfer_completed(
            transfer_id=event.transfer_id or "unknown",
            agreement_id=event.agreement_id or "unknown",
            data_product_id=event.asset_id or "unknown",
            provider_id=settings.participant_id,
            consumer_id="consumer",
            event_id=event.transfer_id,
        )

    return {"status": "ok"}


@router.post("/contract-negotiation", status_code=200)
async def contract_negotiation_event(
    event: ContractNegotiationEvent,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_webhook_scope),
):
    """Record what a negotiation's lifecycle settles on this side.

    Delivered by ``NegotiationEventPublisher`` in the EDC extensions, which
    forwards EDC's own contract-negotiation events. ``type`` is the event name
    upper-snake-cased (``CONTRACT_NEGOTIATION_TERMINATED``), so matching on the
    state word is stable across both sides.

    Both participants run this route and each keeps a different record: the
    provider owns the agreement, the consumer owns the access request. A state
    that means nothing on this side is logged and dropped — this is a projection
    of EDC's state, never the source of truth for it, so an event that arrives
    twice or out of order must not corrupt anything.
    """
    log.info(
        "Contract-negotiation webhook: %s negotiation=%s agreement=%s",
        event.type, event.negotiation_id, event.agreement_id,
    )

    # One transaction for the whole event. The session auto-begins on first use,
    # so the work is done inline and committed once — calling ``db.begin()``
    # after a read would fail on the already-open transaction.
    if "FINALIZED" in event.type and event.agreement_id:
        await upsert_agreement(
            session=db,
            agreement_id=event.agreement_id,
            asset_id=event.payload.get("assetId", ""),
            consumer_id=event.payload.get("consumerId", "consumer"),
            # The agreement names both parties; this connector is only one of
            # them. Taking the provider from our own settings would relabel
            # every agreement the *consumer* connector records as its own.
            provider_id=event.payload.get("providerId") or settings.participant_id,
            policy_snapshot=event.payload.get("policy") or {},
            agreed_at=datetime.now(timezone.utc),
        )
    elif "TERMINATED" in event.type and event.agreement_id:
        # A negotiation can terminate after it produced an agreement — a subject
        # revoking consent, a TTL expiring on a parked negotiation, a
        # counterparty walking away. Marking the agreement settles the PEP's
        # ``/internal/agreements/{id}/status`` answer without waiting for the
        # EDC to be polled.
        await terminate_agreement(
            session=db,
            agreement_id=event.agreement_id,
            reason=f"contract negotiation {event.negotiation_id} terminated",
        )

    await _record_access_request_state(db, event)
    await db.commit()

    # Provenance is emitted after the commit, never inside it: an event must not
    # be recorded for a write that then rolls back.
    if "FINALIZED" in event.type and event.agreement_id:
        prov = getattr(request.app.state, "prov", None)
        if prov:
            await prov.contract_agreement_signed(
                agreement_id=event.agreement_id,
                data_product_id=event.payload.get("assetId", ""),
                provider_id=event.payload.get("providerId") or settings.participant_id,
                consumer_id=event.payload.get("consumerId", "consumer"),
                event_id=event.agreement_id,
            )

    return {"status": "ok"}


async def _record_access_request_state(
    db: AsyncSession, event: ContractNegotiationEvent
) -> None:
    """Reflect the negotiation state onto the consumer's own access request.

    ``GET /consumer/requests`` refreshes status by polling the EDC, which cannot
    tell a consumer *why* a negotiation is sitting where it is. Writing the
    settled states as they arrive means the request list is right the moment the
    negotiation moves, and stays right if the EDC is later unreachable.
    """
    status = next(
        (value for key, value in _ACCESS_REQUEST_STATUS.items() if key in event.type),
        None,
    )
    if status is None or not event.negotiation_id:
        return

    result = await db.execute(
        select(ConsumerAccessRequestORM).where(
            ConsumerAccessRequestORM.negotiation_id == event.negotiation_id
        )
    )
    access_request = result.scalar_one_or_none()
    if access_request is None or access_request.status in _ACCESS_REQUEST_SETTLED:
        return

    access_request.status = status
    if event.agreement_id:
        access_request.contract_agreement_id = event.agreement_id
