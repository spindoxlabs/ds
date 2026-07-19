"""EDC webhook receivers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_settings_dep, require_webhook_scope
from ...schemas.webhooks import ContractNegotiationEvent, TransferProcessEvent
from ...services.agreement_service import upsert_agreement

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


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
    log.info(
        "Contract-negotiation webhook: %s negotiation=%s agreement=%s",
        event.type, event.negotiation_id, event.agreement_id,
    )

    if "FINALIZED" in event.type and event.agreement_id:
        async with db.begin():
            await upsert_agreement(
                session=db,
                agreement_id=event.agreement_id,
                asset_id=event.payload.get("assetId", ""),
                consumer_id=event.payload.get("consumerId", "consumer"),
                provider_id=settings.participant_id,
                policy_snapshot=event.payload.get("policy") or {},
                agreed_at=datetime.now(timezone.utc),
            )

        prov = request.app.state.prov
        await prov.contract_agreement_signed(
            agreement_id=event.agreement_id,
            data_product_id=event.payload.get("assetId", ""),
            provider_id=settings.participant_id,
            consumer_id=event.payload.get("consumerId", "consumer"),
            event_id=event.agreement_id,
        )

    return {"status": "ok"}
