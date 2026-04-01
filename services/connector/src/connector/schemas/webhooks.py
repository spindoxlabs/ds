"""EDC webhook event schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TransferProcessEvent(BaseModel):
    """EDC transfer process state change event."""
    id: str | None = None
    type: str  # e.g. "TransferProcessStarted", "TransferProcessCompleted"
    payload: dict[str, Any] = {}

    @property
    def transfer_id(self) -> str | None:
        return self.payload.get("transferProcessId") or self.id

    @property
    def agreement_id(self) -> str | None:
        return self.payload.get("contractId")

    @property
    def asset_id(self) -> str | None:
        return self.payload.get("assetId")


class ContractNegotiationEvent(BaseModel):
    """EDC contract negotiation state change event."""
    id: str | None = None
    type: str  # e.g. "ContractNegotiationFinalized"
    payload: dict[str, Any] = {}

    @property
    def negotiation_id(self) -> str | None:
        return self.payload.get("contractNegotiationId") or self.id

    @property
    def agreement_id(self) -> str | None:
        return self.payload.get("contractAgreementId")
