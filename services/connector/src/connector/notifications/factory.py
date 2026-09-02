"""Build the active notifier from Settings."""

from __future__ import annotations

import logging

from ..config import Settings
from .base import ConsentNotifier
from .multi import MultiNotifier
from .null import NullNotifier
from .smtp import SmtpNotifier
from .webhook import WebhookNotifier

log = logging.getLogger(__name__)


def build_notifier(settings: Settings) -> ConsentNotifier:
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
            notifiers.append(
                WebhookNotifier(portal_base_url=settings.notify_portal_base_url)
            )
        else:
            log.warning("Unknown notification backend %r — skipped", backend)

    if not notifiers:
        log.info("No notification backends configured — using NullNotifier")
        return NullNotifier()
    if len(notifiers) == 1:
        return notifiers[0]
    return MultiNotifier(notifiers)


def _build_smtp(settings: Settings) -> SmtpNotifier:
    # Read as attributes, not through `getattr` by name. The guard was already
    # correct; addressing the fields by string meant no checker could connect it
    # to the two uses below, which stayed `str | None` at a constructor wanting
    # `str`. Now the same check narrows them.
    host = settings.notify_smtp_host
    from_address = settings.notify_smtp_from
    missing = [
        name
        for name, value in (
            ("notify_smtp_host", host),
            ("notify_smtp_from", from_address),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            f"SMTP backend enabled but missing required settings: "
            f"{', '.join('CONNECTOR_' + m.upper() for m in missing)}"
        )
    assert host is not None and from_address is not None
    return SmtpNotifier(
        host=host,
        port=settings.notify_smtp_port,
        username=settings.notify_smtp_user,
        password=settings.notify_smtp_password,
        from_address=from_address,
        use_tls=settings.notify_smtp_tls,
        portal_base_url=settings.notify_portal_base_url,
    )
