"""Prometheus-style HTTP metrics, shared by every service.

Replaces four byte-identical copies of a per-service `metrics.py`. Three defects
came with those copies, and all three were live:

**The latency metric could not answer a latency question.** It was a bare
``..._sum`` — no ``_count``, no buckets, and **no path label**. So there were no
quantiles at all (no p95, no heatmap, no SLO burn-rate alert, ever), and the one
number it did expose was dominated by the liveness probe: on a live
federated-catalogue, 164 of ~200 requests were ``/health``, so "average request
duration" mostly measured the healthcheck. It is a **histogram** now.

**Unmatched routes leaked unbounded cardinality.** The path label fell back to
``request.url.path`` when no route matched, so every 404 on a URL nobody serves
minted a permanent time series. Measured: four curls at ``/nope-aaa``,
``/nope-bbb``, ``/wp-admin/x`` and ``/.env`` produced four new series. A
vulnerability scanner produces thousands, in the scrape payload and in
Prometheus's index, and neither ever shrinks. Unmatched requests now share the
single label :data:`UNMATCHED`.

**``ds_http_5xx_total`` said nothing new.** ``ds_http_requests_total{status=~"5.."}``
is the same series. Worse, it is an empty metric family whenever a service is
healthy, which reads on a dashboard as a broken query rather than as good news.
Removed.

**Single process, by assumption.** The registry is in-process, which is correct
only because every service pins ``--workers 1``. With more workers each holds its
own counters and a scrape returns whichever one answered. If a service ever needs
more, this needs a shared store, not a bigger worker count.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

#: The path label for a request that matched no route. One series for all of
#: them — see the module docstring.
UNMATCHED = "<unmatched>"

#: Cumulative upper bounds in seconds. The Prometheus client default set, which
#: is what a Grafana panel and `histogram_quantile` expect to find. Sized for
#: HTTP: sub-10ms local reads at the bottom, a DSP round trip in the middle, and
#: `+Inf` catching a crawl that should have timed out.
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _labels(pairs: list[tuple[str, str]]) -> str:
    inner = ",".join(f'{k}="{v}"' for k, v in pairs)
    return "{" + inner + "}"


class HttpMetrics:
    def __init__(
        self, service: str, buckets: tuple[float, ...] = DEFAULT_BUCKETS
    ) -> None:
        self.service = service
        self.started_at = time.time()
        self.buckets = buckets
        # A lock, unlike the copies this replaces. Observation happens on the
        # event loop thread and rendering does too, so contention is nil — but
        # this is a library now, and a caller that observes from a threadpool
        # would otherwise mutate a dict mid-iteration.
        self._lock = threading.Lock()
        # (method, path, status) → count
        self.requests: dict[tuple[str, str, int], int] = {}
        # (method, path) → [per-bucket counts..., +Inf count]
        self._buckets: dict[tuple[str, str], list[int]] = {}
        # (method, path) → (sum_seconds, count)
        self._duration: dict[tuple[str, str], tuple[float, int]] = {}

    def observe(
        self, method: str, path: str, status_code: int, latency_seconds: float
    ) -> None:
        key = (method, path)
        with self._lock:
            self.requests[(method, path, status_code)] = (
                self.requests.get((method, path, status_code), 0) + 1
            )

            counts = self._buckets.get(key)
            if counts is None:
                counts = [0] * (len(self.buckets) + 1)
                self._buckets[key] = counts
            for i, bound in enumerate(self.buckets):
                if latency_seconds <= bound:
                    counts[i] += 1
            counts[-1] += 1  # +Inf

            total, n = self._duration.get(key, (0.0, 0))
            self._duration[key] = (total + latency_seconds, n + 1)

    def render(self) -> str:
        with self._lock:
            requests = dict(self.requests)
            buckets = {k: list(v) for k, v in self._buckets.items()}
            duration = dict(self._duration)

        svc = [("service", self.service)]
        lines = [
            "# HELP ds_service_up Service liveness gauge.",
            "# TYPE ds_service_up gauge",
            f"ds_service_up{_labels(svc)} 1",
            "# HELP ds_service_uptime_seconds Service uptime in seconds.",
            "# TYPE ds_service_uptime_seconds gauge",
            f"ds_service_uptime_seconds{_labels(svc)} "
            f"{time.time() - self.started_at:.3f}",
            "# HELP ds_http_requests_total HTTP requests by method, path and status.",
            "# TYPE ds_http_requests_total counter",
        ]
        for (method, path, status), count in sorted(requests.items()):
            labels = _labels(
                [*svc, ("method", method), ("path", path), ("status", str(status))]
            )
            lines.append(f"ds_http_requests_total{labels} {count}")

        lines.extend(
            [
                "# HELP ds_http_request_duration_seconds HTTP request duration.",
                "# TYPE ds_http_request_duration_seconds histogram",
            ]
        )
        for key in sorted(buckets):
            method, path = key
            base = [*svc, ("method", method), ("path", path)]
            counts = buckets[key]
            # Buckets are cumulative and `+Inf` is mandatory; a histogram
            # missing it is rejected rather than degraded.
            for bound, count in zip(self.buckets, counts):
                labels = _labels([*base, ("le", _fmt_bound(bound))])
                lines.append(f"ds_http_request_duration_seconds_bucket{labels} {count}")
            inf_labels = _labels([*base, ("le", "+Inf")])
            lines.append(
                f"ds_http_request_duration_seconds_bucket{inf_labels} {counts[-1]}"
            )
            total, n = duration.get(key, (0.0, 0))
            lines.append(
                f"ds_http_request_duration_seconds_sum{_labels(base)} {total:.6f}"
            )
            lines.append(f"ds_http_request_duration_seconds_count{_labels(base)} {n}")

        return "\n".join(lines) + "\n"


def _fmt_bound(bound: float) -> str:
    """Prometheus compares `le` as a string; keep it stable across scrapes."""
    return f"{bound:g}"


def route_label(request: Request) -> str:
    """The templated route path, or :data:`UNMATCHED`.

    Never the raw URL. The template (`/catalog/{dataset_iri:path}`) is bounded by
    the route table; the raw URL is bounded by whatever anyone types.
    """
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) and template else UNMATCHED


def install_metrics(app: FastAPI, service: str) -> None:
    metrics = HttpMetrics(service)
    app.state.metrics = metrics

    @app.middleware("http")
    async def collect_http_metrics(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            status_code = response.status_code if response is not None else 500
            metrics.observe(
                request.method,
                route_label(request),
                status_code,
                time.perf_counter() - start,
            )

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(metrics.render(), media_type="text/plain; version=0.0.4")
