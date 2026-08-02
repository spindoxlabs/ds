"""ds-obs — logging configuration and HTTP metrics shared by every service.

Two things every deployable unit needs identically, and which were previously
either duplicated four times (`metrics.py`) or missing entirely (logging).

    from ds_obs import configure_logging, install_metrics

    configure_logging("ds-federated-catalog")   # first, before anything logs
    install_metrics(app, "ds-federated-catalog")

`install_metrics` needs the `fastapi` extra; `configure_logging` does not, so a
CLI can use it without pulling a web framework in.
"""
from .logging import JsonFormatter, ProbeAccessFilter, configure_logging

__all__ = [
    "JsonFormatter",
    "ProbeAccessFilter",
    "configure_logging",
    "install_metrics",
    "HttpMetrics",
    "route_label",
    "UNMATCHED",
]


def __getattr__(name: str):
    """Defer the metrics import so `configure_logging` works without FastAPI.

    A CLI importing `ds_obs` should not fail because a web framework it will
    never use is absent.
    """
    if name in {"install_metrics", "HttpMetrics", "route_label", "UNMATCHED"}:
        from . import metrics

        return getattr(metrics, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
