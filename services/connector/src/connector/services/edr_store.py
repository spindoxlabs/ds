"""Where a transfer's EDR is kept once its EDC has delivered it.

EDC 0.18.0's v5 management API has no EDR endpoint. A transfer this connector
starts names a callback address (``consumer_service.edr_callback_address``); the
``TransferProcessStarted`` event EDC posts there carries the EDR, the webhook
stores it with :meth:`EdrStore.save`, and whoever needs it asks
:meth:`EdrStore.wait_for`.

The event and the ``STARTED`` state are delivered independently — the callback
dispatch is asynchronous (``CallbackEventDispatcher``, non-transactional) — so a
reader that has just seen ``STARTED`` waits a bounded time for the row rather
than reporting "no EDR" for one that is a few milliseconds away.
"""

from __future__ import annotations

import asyncio
import time

from ds_edc import EdrResponse, TransferProcessStartedEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import EdrEntryORM


class EdrNotReceived(LookupError):
    """No EDR arrived for the transfer within the wait."""

    def __init__(self, transfer_id: str, waited: float):
        self.transfer_id = transfer_id
        self.waited = waited
        super().__init__(
            f"no EDR was delivered for transfer {transfer_id!r} within {waited:g}s "
            "— check that the EDC can reach CONNECTOR_EDC_CALLBACK_URL and that "
            "its vault holds the callback key"
        )


async def save_started_event(
    session: AsyncSession, event: TransferProcessStartedEvent
) -> EdrEntryORM:
    """Store (or refresh) the EDR a ``TransferProcessStarted`` event carries.

    Raises ``ValueError`` when the event has no usable EDR — the caller answers
    that as a refusal, never as a stored empty row.
    """
    if not event.transfer_id:
        raise ValueError("TransferProcessStarted without a transferProcessId")
    edr = event.edr()
    row = await session.get(EdrEntryORM, event.transfer_id)
    if row is None:
        row = EdrEntryORM(transfer_id=event.transfer_id)
        session.add(row)
    row.participant_context_id = event.participant_context_id
    row.agreement_id = event.agreement_id
    row.asset_id = event.asset_id
    row.endpoint = edr.endpoint
    row.auth_type = edr.auth_type
    row.authorization = edr.authorization
    row.data_address = event.data_address
    row.event_id = event.id
    return row


def _to_edr(row: EdrEntryORM) -> EdrResponse:
    return EdrResponse(
        endpoint=row.endpoint,
        auth_type=row.auth_type or "bearer",
        authorization=row.authorization,
    )


class EdrStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        wait_timeout: float = 30.0,
        poll_interval: float = 0.25,
    ):
        self._sessions = session_factory
        self._wait_timeout = wait_timeout
        self._poll_interval = poll_interval

    async def get(self, transfer_id: str) -> EdrResponse | None:
        async with self._sessions() as session:
            row = await session.get(EdrEntryORM, transfer_id)
            return _to_edr(row) if row is not None else None

    async def get_many(self, transfer_ids: list[str]) -> dict[str, EdrResponse]:
        if not transfer_ids:
            return {}
        async with self._sessions() as session:
            result = await session.execute(
                select(EdrEntryORM).where(EdrEntryORM.transfer_id.in_(transfer_ids))
            )
            return {row.transfer_id: _to_edr(row) for row in result.scalars()}

    async def wait_for(
        self, transfer_id: str, timeout: float | None = None
    ) -> EdrResponse:
        waited = self._wait_timeout if timeout is None else timeout
        deadline = time.monotonic() + waited
        while True:
            edr = await self.get(transfer_id)
            if edr is not None:
                return edr
            if time.monotonic() >= deadline:
                raise EdrNotReceived(transfer_id, waited)
            await asyncio.sleep(self._poll_interval)
