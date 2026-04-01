"""Webhook notifier — POSTs JSON to consent.notification_url."""
from __future__ import annotations

import logging

import httpx

from ..db.models import ConsentRequestORM
from .base import ConsentNotifier

log = logging.getLogger(__name__)


class WebhookNotifier(ConsentNotifier):
    """POSTs a JSON consent event to the notification_url stored on the consent record."""

    def __init__(self, portal_base_url: str = "https://portal.dataspaces.localhost") -> None:
        self._portal_base_url = portal_base_url.rstrip("/")

    async def notify_requested(self, consent: ConsentRequestORM) -> None:
        if not consent.notification_url:
            return
        payload = self._build_payload("consent.requested", consent)
        await self._post(consent.notification_url, payload)

    async def notify_status_changed(self, consent: ConsentRequestORM) -> None:
        if not consent.notification_url:
            return
        payload = self._build_payload("consent.status_changed", consent)
        await self._post(consent.notification_url, payload)

    def _build_payload(self, event: str, consent: ConsentRequestORM) -> dict:
        return {
            "event": event,
            "consent_id": consent.id,
            "subject_id": consent.subject_id,
            "dataset_id": consent.dataset_id,
            "consumer_id": consent.consumer_id,
            "status": consent.status,
            "portal_url": f"{self._portal_base_url}/consent/{consent.id}",
        }

    async def _post(self, url: str, payload: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            log.info("Webhook notification delivered to %s", url)
        except Exception as exc:
            log.warning("Webhook notification failed to %s: %s", url, exc)
