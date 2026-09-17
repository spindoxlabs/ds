"""EDC webhook event schemas.

## The two agreement ids, and which one correlates

A contract agreement has **two** identifiers, and conflating them is why a
provider-side trace and a consumer-side trace of the same exchange could not be
joined:

| Name on the wire | Source | Scope |
|---|---|---|
| ``contractAgreementId`` | ``ContractAgreement.getId()`` | **local** — this
  runtime's entity id. Provider and consumer hold *different* values for the
  same agreement |
| ``dspAgreementId`` | ``ContractAgreement.getAgreementId()`` | **shared** —
  the DSP agreement id both participants can name |

Verified against a live exchange; see the comment in
``services/edc-extensions/.../NegotiationEventPublisher.java``, which emits both
for that reason.

**Correlate on ``dsp_agreement_id``. Address the local control plane with
``agreement_id``.** The transfer event's ``contractId`` is the id the transfer
was *started* with, which is the consumer's local one — so it joins to the
consumer's negotiation event and to nothing on the provider side. Only
``dspAgreementId`` spans both, which is why a data-plane request carries it.

Before this docstring existed the shared id had no accessor at all, and the
connector reached past the model into ``event.payload["dspAgreementId"]`` — the
usual sign that a vocabulary was never settled.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .schemas import EdrResponse


class TransferProcessEvent(BaseModel):
    """EDC transfer process state change event."""

    id: str | None = None
    type: str
    payload: dict[str, Any] = {}

    @property
    def transfer_id(self) -> str | None:
        return self.payload.get("transferProcessId") or self.id

    @property
    def agreement_id(self) -> str | None:
        """The agreement this transfer was started against — **local** scope."""
        return self.payload.get("contractId")

    @property
    def asset_id(self) -> str | None:
        return self.payload.get("assetId")


class ContractNegotiationEvent(BaseModel):
    """EDC contract negotiation state change event."""

    id: str | None = None
    type: str
    payload: dict[str, Any] = {}

    @property
    def negotiation_id(self) -> str | None:
        return self.payload.get("contractNegotiationId") or self.id

    @property
    def agreement_id(self) -> str | None:
        """This runtime's own agreement entity id — **local** scope.

        Right for addressing this control plane; wrong for correlating with the
        counterparty, which holds a different value. Use
        :attr:`dsp_agreement_id` for that.
        """
        return self.payload.get("contractAgreementId")

    @property
    def dsp_agreement_id(self) -> str | None:
        """The DSP agreement id — **shared** scope, the correlation key.

        Present only on ``FINALIZED``: it is read off the agreement, and there is
        no agreement before one is signed.
        """
        return self.payload.get("dspAgreementId")


class TransferProcessStartedEvent(BaseModel):
    """The ``TransferProcessStarted`` envelope EDC posts to a callback address.

    Its shape is EDC's own ``EventEnvelope`` serialised by Jackson — ``id``,
    ``at``, ``payload`` and ``type`` — not the compact JSON-LD a management
    response carries. On the consumer side the payload's ``dataAddress`` is the
    **EDR**: the data plane's endpoint and the bearer that opens it.
    """

    id: str | None = None
    at: int | None = None
    type: str
    payload: dict[str, Any] = {}

    @property
    def is_started(self) -> bool:
        return self.type == "TransferProcessStarted"

    @property
    def transfer_id(self) -> str | None:
        value = self.payload.get("transferProcessId")
        return str(value) if value else None

    @property
    def agreement_id(self) -> str | None:
        """The agreement the transfer was started against — **local** scope."""
        value = self.payload.get("contractId")
        return str(value) if value else None

    @property
    def asset_id(self) -> str | None:
        value = self.payload.get("assetId")
        return str(value) if value else None

    @property
    def participant_context_id(self) -> str | None:
        value = self.payload.get("participantContextId")
        return str(value) if value else None

    @property
    def data_address(self) -> dict[str, Any]:
        value = self.payload.get("dataAddress")
        return value if isinstance(value, dict) else {}

    def edr(self) -> EdrResponse:
        """The EDR, or ``ValueError`` when the event carries none."""
        return EdrResponse.from_edc(self.data_address)
