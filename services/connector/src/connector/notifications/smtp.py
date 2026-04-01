"""SMTP email notifier using aiosmtplib."""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from ..db.models import ConsentRequestORM
from .base import ConsentNotifier

log = logging.getLogger(__name__)

_STATUS_LABELS = {
    "pending": "Pending Review",
    "granted": "Approved",
    "rejected": "Rejected",
    "revoked": "Revoked",
}


class SmtpNotifier(ConsentNotifier):
    """Sends HTML consent notification emails via SMTP."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        use_tls: bool = True,
        portal_base_url: str = "https://portal.dataspaces.localhost",
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls
        self._portal_base_url = portal_base_url.rstrip("/")

    async def notify_requested(self, consent: ConsentRequestORM) -> None:
        subject = f"New data access request — {consent.dataset_id}"
        portal_url = f"{self._portal_base_url}/consent/{consent.id}"
        body = self._render_requested(consent, portal_url)
        await self._send(to=consent.subject_id, subject=subject, body=body)

    async def notify_status_changed(self, consent: ConsentRequestORM) -> None:
        status_label = _STATUS_LABELS.get(consent.status, consent.status)
        subject = f"Consent request {status_label.lower()} — {consent.dataset_id}"
        portal_url = f"{self._portal_base_url}/consent/{consent.id}"
        body = self._render_status_changed(consent, portal_url, status_label)
        await self._send(to=consent.subject_id, subject=subject, body=body)

    async def _send(self, to: str, subject: str, body: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to
        msg.attach(MIMEText(body, "html"))
        try:
            await aiosmtplib.send(
                msg,
                hostname=self._host,
                port=self._port,
                username=self._username or "",
                password=self._password or "",
                start_tls=self._use_tls,
            )
            log.info("Consent notification sent to %s: %s", to, subject)
        except Exception as exc:
            log.warning("SMTP notification failed for %s: %s", to, exc)

    def _render_requested(self, consent: ConsentRequestORM, portal_url: str) -> str:
        purpose = ", ".join(consent.purpose or []) or "Not specified"
        return f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
<h2 style="color:#1a56db">New Data Access Request</h2>
<p>A new consent request has been submitted for access to your data.</p>
<table style="border-collapse:collapse;width:100%;margin:16px 0">
  <tr><td style="padding:8px;color:#6b7280;width:140px">Dataset</td>
      <td style="padding:8px;font-weight:500">{consent.dataset_id}</td></tr>
  <tr><td style="padding:8px;color:#6b7280">Requester</td>
      <td style="padding:8px">{consent.consumer_id}</td></tr>
  <tr><td style="padding:8px;color:#6b7280">Purpose</td>
      <td style="padding:8px">{purpose}</td></tr>
  {f'<tr><td style="padding:8px;color:#6b7280">Message</td><td style="padding:8px">{consent.message}</td></tr>' if consent.message else ''}
</table>
<a href="{portal_url}" style="display:inline-block;background:#1a56db;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:500">
  Review Request
</a>
<p style="margin-top:24px;color:#9ca3af;font-size:12px">
  This notification was sent by the dataspaces platform. Do not reply to this email.
</p>
</body></html>
"""

    def _render_status_changed(
        self, consent: ConsentRequestORM, portal_url: str, status_label: str
    ) -> str:
        status_color = {
            "Approved": "#059669",
            "Rejected": "#dc2626",
            "Revoked": "#d97706",
        }.get(status_label, "#6b7280")
        return f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
<h2 style="color:#111827">Consent Request Update</h2>
<p>The status of a consent request for your data has changed.</p>
<table style="border-collapse:collapse;width:100%;margin:16px 0">
  <tr><td style="padding:8px;color:#6b7280;width:140px">Dataset</td>
      <td style="padding:8px;font-weight:500">{consent.dataset_id}</td></tr>
  <tr><td style="padding:8px;color:#6b7280">Requester</td>
      <td style="padding:8px">{consent.consumer_id}</td></tr>
  <tr><td style="padding:8px;color:#6b7280">New Status</td>
      <td style="padding:8px;font-weight:600;color:{status_color}">{status_label}</td></tr>
</table>
<a href="{portal_url}" style="display:inline-block;background:#1a56db;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:500">
  View Details
</a>
<p style="margin-top:24px;color:#9ca3af;font-size:12px">
  This notification was sent by the dataspaces platform. Do not reply to this email.
</p>
</body></html>
"""
