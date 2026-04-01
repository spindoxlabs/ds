"""MultiNotifier — fans out to a list of notifiers concurrently."""
from __future__ import annotations

import asyncio
import logging

from ..db.models import ConsentRequestORM
from .base import ConsentNotifier

log = logging.getLogger(__name__)


class MultiNotifier(ConsentNotifier):
    """Calls all configured notifiers concurrently. Individual failures are logged and swallowed."""

    def __init__(self, notifiers: list[ConsentNotifier]) -> None:
        self._notifiers = notifiers

    async def notify_requested(self, consent: ConsentRequestORM) -> None:
        await self._fan_out("notify_requested", consent)

    async def notify_status_changed(self, consent: ConsentRequestORM) -> None:
        await self._fan_out("notify_status_changed", consent)

    async def _fan_out(self, method: str, consent: ConsentRequestORM) -> None:
        async def _call(notifier: ConsentNotifier) -> None:
            try:
                await getattr(notifier, method)(consent)
            except Exception as exc:
                log.warning(
                    "Notifier %s.%s failed for consent %s: %s",
                    type(notifier).__name__,
                    method,
                    consent.id,
                    exc,
                )

        await asyncio.gather(*(_call(n) for n in self._notifiers))
