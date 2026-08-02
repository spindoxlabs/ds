"""One logging configuration for every service in the platform.

**Nothing configured logging before this.** Only the CLI entry points called
``basicConfig``; the FastAPI services called nothing at all, so their loggers
fell through to Python's handler of last resort — which emits **WARNING and
above, and nothing else**. Every ``log.info`` in every service went nowhere.

The effect was not "slightly less detail". It inverted the signal: uvicorn's own
access log ran at INFO through its own configuration, so a container's log was
hundreds of ``GET /health 200`` lines and no application events, while a
*successful* crawl, a token refresh or a completed sync was indistinguishable
from that work never having run. Only failures spoke.

Three env vars, all optional and all read here rather than in each service's
``Settings`` — logging is a property of the process, not of the domain:

``DS_LOG_LEVEL``
    ``DEBUG`` … ``CRITICAL``. Default ``INFO``.
``DS_LOG_FORMAT``
    ``text`` (default) or ``json``. JSON is one object per line, for a log
    shipper. Text is for a person reading ``docker logs``.
``DS_LOG_ACCESS_HEALTH``
    Default false: **successful** access-log lines for ``/health`` and
    ``/metrics`` are dropped. A liveness probe every 10s and a scrape every 15s
    are the highest-volume, lowest-information lines a service emits, and they
    were burying everything else. Non-2xx probes are always kept — a *failing*
    healthcheck is exactly the line you need.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}

#: Access-log paths suppressed at 2xx. Not configurable per path on purpose:
#: the list is "endpoints an automated prober calls on a timer", and it is not
#: meant to grow into a way of hiding traffic.
_PROBE_PATHS = ("/health", "/metrics")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the service name on every record."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Anything passed via `extra=` — structured context a caller chose to
        # attach. Skipped for the text formatter, which has nowhere to put it.
        for key, value in record.__dict__.items():
            if key.startswith("ds_"):
                payload[key[3:]] = value
        return json.dumps(payload, default=str)


class ProbeAccessFilter(logging.Filter):
    """Drop uvicorn access lines for successful liveness and scrape requests.

    The status code is parsed out of uvicorn's own args rather than the
    formatted message, because the message is not built until a handler asks for
    it. When the shape is not what we expect the line is **kept** — a filter that
    guesses wrong should lose information in the direction of noise, not silence.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        path, status = args[2], args[4]
        if not isinstance(path, str):
            return True
        # `path` is the raw request target, so strip any query string before
        # matching — `/health?x=1` is still a probe.
        if path.split("?", 1)[0] not in _PROBE_PATHS:
            return True
        try:
            return not (200 <= int(status) < 300)
        except (TypeError, ValueError):
            return True


def configure_logging(service: str, *, level: str | None = None) -> None:
    """Install the platform's logging configuration. Idempotent.

    Call it **first** in the application factory, before anything that logs.
    Handlers already on the root logger are replaced, so calling it twice (a
    reload, a test) does not double every line.

    ``uvicorn``'s own loggers are re-pointed at the same handler rather than
    left alone. Otherwise a container emits two formats — uvicorn's and ours —
    which is what "coordinated" has to rule out.
    """
    resolved = (level or os.getenv("DS_LOG_LEVEL") or "INFO").upper()
    if resolved not in _LEVELS:
        resolved = "INFO"

    if (os.getenv("DS_LOG_FORMAT") or "text").strip().lower() == "json":
        formatter: logging.Formatter = JsonFormatter(service)
    else:
        formatter = logging.Formatter(
            f"%(asctime)s %(levelname)-8s [{service}] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(resolved)

    access = logging.getLogger("uvicorn.access")
    access.filters = [f for f in access.filters if not isinstance(f, ProbeAccessFilter)]
    if not _env_flag("DS_LOG_ACCESS_HEALTH"):
        access.addFilter(ProbeAccessFilter())

    # httpx logs every outbound request at INFO. In a service that crawls, syncs
    # or fans out to several counterparties that is one line per hop and it
    # drowns the events those hops belong to. WARNING keeps the failures.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(
            logging.DEBUG if resolved == "DEBUG" else logging.WARNING
        )
