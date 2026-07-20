"""EDC Management API request/response Pydantic models.

Re-exported from the shared ``ds_edc`` library.  Kept as a thin shim so
existing intra-service imports (``from ..schemas.edc import ...``) continue
to resolve without a global find-and-replace.
"""
from ds_edc.schemas import (  # noqa: F401
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
