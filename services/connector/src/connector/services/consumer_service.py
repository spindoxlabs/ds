"""Consumer-side service: catalog → negotiate → transfer → EDR."""
from __future__ import annotations

import inspect
import logging

from ..clients.edc_management import EdcManagementClient
from ..registry.participants import ParticipantRegistry, UnknownParticipantError
from ..schemas.edc import (
    CatalogRequest,
    EdrResponse,
    FlowRequest,
    FlowResult,
    NegotiationRequest,
    TransferRequest,
)
from .prov_bridge import ProvBridge

log = logging.getLogger(__name__)


class ConsumerService:
    def __init__(
        self,
        consumer_edc: EdcManagementClient,
        registry: ParticipantRegistry,
        prov: ProvBridge,
        poll_interval: float = 2.0,
        negotiation_timeout: float = 120.0,
        transfer_timeout: float = 120.0,
        participant_id: str = "consumer",
        provider_id: str = "provider",
    ):
        self._edc = consumer_edc
        self._registry = registry
        self._prov = prov
        self._poll_interval = poll_interval
        self._neg_timeout = negotiation_timeout
        self._tx_timeout = transfer_timeout
        self._participant_id = participant_id
        self._provider_id = provider_id

    async def request_catalog(self, counter_party_address: str) -> dict:
        try:
            result = self._registry.validate(counter_party_address)
            if inspect.isawaitable(result):
                await result
        except UnknownParticipantError:
            log.warning(
                "Counter-party %s not in registry — proceeding anyway (open mode)",
                counter_party_address,
            )
        req = CatalogRequest(counter_party_address=counter_party_address)
        return await self._edc.request_catalog(req)

    async def negotiate(
        self,
        counter_party_address: str,
        offer_id: str,
        asset_id: str,
        assigner: str,
        odrl_policy: dict | None = None,
    ) -> str:
        req = NegotiationRequest(
            counter_party_address=counter_party_address,
            offer_id=offer_id,
            asset_id=asset_id,
            assigner=assigner,
            odrl_policy=odrl_policy,
        )
        return await self._edc.start_negotiation(req)

    async def transfer(
        self,
        contract_agreement_id: str,
        counter_party_address: str,
        asset_id: str,
        connector_id: str,
    ) -> str:
        req = TransferRequest(
            contract_agreement_id=contract_agreement_id,
            counter_party_address=counter_party_address,
            asset_id=asset_id,
            connector_id=connector_id,
        )
        return await self._edc.start_transfer(req)

    async def get_edr(self, transfer_id: str) -> EdrResponse:
        return await self._edc.get_edr(transfer_id)

    async def run_flow(self, req: FlowRequest) -> FlowResult:
        """Full consumer flow: catalog → negotiate → transfer → EDR."""
        # 1. Negotiate
        negotiation_id = await self.negotiate(
            counter_party_address=req.counter_party_address,
            offer_id=req.asset_id,   # EDC v3 uses offer_id = asset_id until catalog lookup
            asset_id=req.asset_id,
            assigner=req.assigner,
        )
        log.info("Started negotiation %s", negotiation_id)

        # 2. Poll until FINALIZED
        neg_state = await self._edc.poll_negotiation(
            negotiation_id,
            poll_interval=self._poll_interval,
            timeout=self._neg_timeout,
        )
        if neg_state.state not in ("FINALIZED", "VERIFIED", "AGREED") or not neg_state.contract_agreement_id:
            raise RuntimeError(
                f"Negotiation {negotiation_id} failed: state={neg_state.state} "
                f"error={neg_state.error_detail}"
            )

        agreement_id = neg_state.contract_agreement_id
        log.info("Negotiation FINALIZED, agreement %s", agreement_id)

        # 3. Emit PROV-O
        await self._prov.contract_agreement_signed(
            agreement_id=agreement_id,
            data_product_id=req.asset_id,
            provider_id=req.assigner,
            consumer_id=self._participant_id,
            event_id=agreement_id,
        )

        # 4. Transfer
        transfer_id = await self.transfer(
            contract_agreement_id=agreement_id,
            counter_party_address=req.counter_party_address,
            asset_id=req.asset_id,
            connector_id=req.assigner,
        )
        log.info("Started transfer %s", transfer_id)

        # 5. Poll until STARTED
        tx_state = await self._edc.poll_transfer(
            transfer_id,
            poll_interval=self._poll_interval,
            timeout=self._tx_timeout,
        )
        if tx_state.state not in ("STARTED",):
            raise RuntimeError(
                f"Transfer {transfer_id} failed: state={tx_state.state} "
                f"error={tx_state.error_detail}"
            )

        # 6. Fetch EDR
        edr = await self._edc.get_edr(transfer_id)
        log.info("Got EDR for transfer %s", transfer_id)

        # 7. Emit DataTransferCompleted PROV-O
        await self._prov.data_transfer_completed(
            transfer_id=transfer_id,
            agreement_id=agreement_id,
            data_product_id=req.asset_id,
            provider_id=req.assigner,
            consumer_id=self._participant_id,
            event_id=transfer_id,
        )

        return FlowResult(
            negotiation_id=negotiation_id,
            contract_agreement_id=agreement_id,
            transfer_id=transfer_id,
            edr=edr,
        )
