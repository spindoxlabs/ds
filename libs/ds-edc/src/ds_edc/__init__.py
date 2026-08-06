"""Shared EDC Management API v3 client and Pydantic models."""

from .client import EdcManagementClient, EdcPollTimeout
from .schemas import (
    DATASPACE_PROTOCOL,
    DSP_PATH_SEGMENT,
    DSP_VERSION,
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
    "DSP_PATH_SEGMENT",
    "DSP_VERSION",
    "AssetCreate",
    "CatalogRequest",
    "ContractDefCreate",
    "ContractNegotiationEvent",
    "DataAddress",
    "EdcManagementClient",
    "EdcPollTimeout",
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
