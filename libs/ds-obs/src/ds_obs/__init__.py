"""ds-obs — logging configuration and HTTP metrics shared by every service.

Two things every deployable unit needs identically, and which were previously
either duplicated four times (`metrics.py`) or missing entirely (logging).

    from ds_obs import configure_logging, install_metrics, install_tracing

    configure_logging("ds-federated-catalog")   # first, before anything logs
    install_metrics(app, "ds-federated-catalog")
    install_tracing(app, "ds-federated-catalog")

`install_metrics` needs the `fastapi` extra and `install_tracing` needs `fastapi`
plus `tracing`; `configure_logging` needs neither, so a CLI can use it without
pulling a web framework or an OTLP exporter in.
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
    "AGREEMENT_ID_ATTRIBUTE",
    "agreement_scope",
    "configure_tracing",
    "correlate_agreement",
    "current_agreement",
    "install_tracing",
    "tracing_endpoint",
]

_METRICS = {"install_metrics", "HttpMetrics", "route_label", "UNMATCHED"}
_TRACING = {
    "AGREEMENT_ID_ATTRIBUTE",
    "agreement_scope",
    "configure_tracing",
    "correlate_agreement",
    "current_agreement",
    "install_tracing",
    "tracing_endpoint",
}


def __getattr__(name: str):
    """Defer the optional imports so `configure_logging` needs neither extra.

    A CLI importing `ds_obs` should not fail because a web framework or an OTLP
    exporter it will never use is absent.
    """
    if name in _METRICS:
        from . import metrics

        return getattr(metrics, name)
    if name in _TRACING:
        from . import tracing

        return getattr(tracing, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
