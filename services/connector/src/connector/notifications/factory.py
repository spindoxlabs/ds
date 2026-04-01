"""Build the active notifier from Settings."""
from __future__ import annotations

import logging

from .base import ConsentNotifier
from .multi import MultiNotifier
from .null import NullNotifier
from .smtp import SmtpNotifier
from .webhook import WebhookNotifier

log = logging.getLogger(__name__)


def build_notifier(settings: "Settings") -> ConsentNotifier:  # noqa: F821
    """Construct the active notifier from CONNECTOR_NOTIFY_BACKENDS.

    Returns NullNotifier when no backends are configured.
    Returns the single notifier directly when only one backend is enabled.
    Returns MultiNotifier when multiple backends are enabled.
    """
    backends_raw: str = getattr(settings, "notify_backends", "") or ""
    backends = [b.strip() for b in backends_raw.split(",") if b.strip()]

    notifiers: list[ConsentNotifier] = []

    for backend in backends:
        if backend == "smtp":
            notifiers.append(_build_smtp(settings))
        elif backend == "webhook":
            notifiers.append(WebhookNotifier(portal_base_url=settings.notify_portal_base_url))
        else:
            log.warning("Unknown notification backend %r — skipped", backend)

    if not notifiers:
        log.info("No notification backends configured — using NullNotifier")
        return NullNotifier()
    if len(notifiers) == 1:
        return notifiers[0]
    return MultiNotifier(notifiers)


def _build_smtp(settings: "Settings") -> SmtpNotifier:  # noqa: F821
    missing = [
        name
        for name in ("notify_smtp_host", "notify_smtp_from")
        if not getattr(settings, name, None)
    ]
    if missing:
        raise ValueError(
            f"SMTP backend enabled but missing required settings: "
            f"{', '.join('CONNECTOR_' + m.upper() for m in missing)}"
        )
    return SmtpNotifier(
        host=settings.notify_smtp_host,
        port=settings.notify_smtp_port,
        username=settings.notify_smtp_user,
        password=settings.notify_smtp_password,
        from_address=settings.notify_smtp_from,
        use_tls=settings.notify_smtp_tls,
        portal_base_url=settings.notify_portal_base_url,
    )
