"""Abstract base class for consent notifiers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..db.models import ConsentRequestORM


class ConsentNotifier(ABC):
    """Interface for sending consent lifecycle notifications to data subjects."""

    @abstractmethod
    async def notify_requested(self, consent: ConsentRequestORM) -> None:
        """Notify subject that a new consent request was created."""
        ...

    @abstractmethod
    async def notify_status_changed(self, consent: ConsentRequestORM) -> None:
        """Notify subject that their consent status changed (granted/rejected/revoked)."""
        ...
