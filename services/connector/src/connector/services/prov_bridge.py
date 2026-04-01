"""Maps connector events to PROV-O domain events and emits them."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..clients.provenance import ProvenanceClient

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    ) -> None:
        await self._prov.emit_event({
            "event_type": "CataloguePublished",
            "event_id": event_id,
            "occurred_at": _now(),
            "data_product_id": data_product_id,
            "provider_did": f"did:web:{self._participant_id}",
            "title": title,
            "description": description,
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
            "provider_did": f"did:web:{provider_id}",
            "consumer_did": f"did:web:{consumer_id}",
            "policy_hash": policy_hash,
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
            "provider_did": f"did:web:{provider_id}",
            "consumer_did": f"did:web:{consumer_id}",
            "bytes_transferred": bytes_transferred,
            "derived_dataset_iri": derived_dataset_iri,
        })

    async def usage_obligation_fulfilled(
        self,
        agreement_id: str,
        consumer_id: str,
        obligation_type: str,
        event_id: str | None = None,
    ) -> None:
        await self._prov.emit_event({
            "event_type": "UsageObligationFulfilled",
            "event_id": event_id,
            "occurred_at": _now(),
            "agreement_id": agreement_id,
            "consumer_did": f"did:web:{consumer_id}",
            "obligation_type": obligation_type,
        })
