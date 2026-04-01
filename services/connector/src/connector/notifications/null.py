"""No-op notifier — used when no backends are configured."""
from __future__ import annotations

from ..db.models import ConsentRequestORM
from .base import ConsentNotifier


class NullNotifier(ConsentNotifier):
    async def notify_requested(self, consent: ConsentRequestORM) -> None:
        pass

    async def notify_status_changed(self, consent: ConsentRequestORM) -> None:
        pass
