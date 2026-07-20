"""Shared EDC Management API v3 client and Pydantic models."""

from .client import EdcManagementClient
from .schemas import (
    DATASPACE_PROTOCOL,
    AssetCreate,
    CatalogRequest,
    ContractDefCreate,
    DataAddress,
    EdrResponse,
    FlowRequest,
    FlowResult,
    NegotiationRequest,
    NegotiationState,
    PolicyCreate,
    SyncResult,
    TransferRequest,
    TransferState,
)
from .webhooks import ContractNegotiationEvent, TransferProcessEvent

__all__ = [
    "DATASPACE_PROTOCOL",
    "AssetCreate",
    "CatalogRequest",
    "ContractDefCreate",
    "ContractNegotiationEvent",
    "DataAddress",
    "EdcManagementClient",
    "EdrResponse",
    "FlowRequest",
    "FlowResult",
    "NegotiationRequest",
    "NegotiationState",
    "PolicyCreate",
    "SyncResult",
    "TransferProcessEvent",
    "TransferRequest",
    "TransferState",
]
