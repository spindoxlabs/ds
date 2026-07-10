"""Consumer-side service: catalog → negotiate → transfer → EDR."""
from __future__ import annotations

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


def _id_of(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("@id") or value.get("id") or "")
    return ""


def _strip_prefix(value: str) -> str:
    return value.removeprefix("odrl:")


def _normalise_odrl(value: object) -> object:
    if isinstance(value, list):
        return [_normalise_odrl(item) for item in value]
    if isinstance(value, str):
        return _strip_prefix(value)
    if not isinstance(value, dict):
        return value

    key_map = {
        "odrl:permission": "permission",
        "odrl:prohibition": "prohibition",
        "odrl:obligation": "obligation",
        "odrl:assigner": "assigner",
        "odrl:assignee": "assignee",
        "odrl:target": "target",
        "odrl:action": "action",
        "odrl:constraint": "constraint",
        "odrl:leftOperand": "leftOperand",
        "odrl:operator": "operator",
        "odrl:rightOperand": "rightOperand",
    }
    normalised: dict[str, object] = {}
    for key, item in value.items():
        if key == "@context":
            continue
        out_key = key_map.get(key, key)
        if out_key == "@type" and isinstance(item, str):
            normalised[out_key] = _strip_prefix(item)
        else:
            normalised[out_key] = _normalise_odrl(item)
    return normalised


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
        allow_unknown_participants: bool = False,
    ):
        self._edc = consumer_edc
        self._registry = registry
        self._prov = prov
        self._poll_interval = poll_interval
        self._neg_timeout = negotiation_timeout
        self._tx_timeout = transfer_timeout
        self._participant_id = participant_id
        self._provider_id = provider_id
        self._allow_unknown_participants = allow_unknown_participants

    async def request_catalog(self, counter_party_address: str, counter_party_id: str | None = None) -> dict:
        # Validate participant if registry is populated
        try:
            self._registry.validate(counter_party_address)
        except UnknownParticipantError:
            if not self._allow_unknown_participants:
                raise
            log.warning("Counter-party %s not in registry — proceeding anyway", counter_party_address)
        req = CatalogRequest(
            counter_party_address=counter_party_address,
            counter_party_id=counter_party_id or self._provider_id,
        )
        return await self._edc.request_catalog(req)

    async def negotiate(
        self,
        counter_party_address: str,
        offer_id: str,
        asset_id: str,
        assigner: str,
        odrl_policy: dict | None = None,
    ) -> str:
        catalog_policy = await self._catalog_policy(counter_party_address, asset_id)
        if catalog_policy:
            odrl_policy = catalog_policy
            offer_id = str(catalog_policy.get("@id") or offer_id)
            assigner = _id_of(catalog_policy.get("assigner")) or _id_of(catalog_policy.get("odrl:assigner")) or assigner
        elif odrl_policy:
            odrl_policy = self._fallback_policy(odrl_policy, offer_id, asset_id, assigner)
        req = NegotiationRequest(
            counter_party_address=counter_party_address,
            offer_id=offer_id,
            asset_id=asset_id,
            assigner=assigner,
            odrl_policy=odrl_policy,
        )
        return await self._edc.start_negotiation(req)

    async def _catalog_policy(self, counter_party_address: str, asset_id: str) -> dict | None:
        catalog = await self.request_catalog(counter_party_address)
        for dataset in catalog.get("dataset", []):
            if dataset.get("@id") != asset_id and dataset.get("id") != asset_id:
                continue
            policies = dataset.get("hasPolicy") or dataset.get("odrl:hasPolicy") or []
            policy = None
            if isinstance(policies, dict):
                policy = policies
            if policies:
                policy = policies[0]
            if not isinstance(policy, dict):
                return None
            return {
                "@context": ["http://www.w3.org/ns/odrl.jsonld"],
                "@type": "Offer",
                "@id": policy.get("@id") or f"{asset_id}#offer",
                "assigner": self._provider_id,
                "target": asset_id,
                "permission": policy.get("permission") or policy.get("odrl:permission") or [],
            }
        return None

    def _fallback_policy(self, policy: dict, offer_id: str, asset_id: str, assigner: str) -> dict:
        normalised = _normalise_odrl(policy)
        if not isinstance(normalised, dict):
            normalised = {}
        normalised["@context"] = ["http://www.w3.org/ns/odrl.jsonld"]
        normalised["@type"] = "Offer"
        normalised["@id"] = str(normalised.get("@id") or offer_id)
        normalised["assigner"] = _id_of(normalised.get("assigner")) or assigner
        normalised["target"] = _id_of(normalised.get("target")) or asset_id
        normalised.setdefault("permission", [])
        return normalised

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
