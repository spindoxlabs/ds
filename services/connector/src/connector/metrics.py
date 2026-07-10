"""Minimal Prometheus-style in-process metrics."""
from __future__ import annotations

import time
from collections import Counter
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response


class HttpMetrics:
    def __init__(self, service: str) -> None:
        self.service = service
        self.started_at = time.time()
        self.requests: Counter[tuple[str, str, int]] = Counter()
        self.errors: Counter[tuple[str, str, int]] = Counter()
        self.latency_seconds_sum = 0.0

    def observe(self, method: str, path: str, status_code: int, latency_seconds: float) -> None:
        labels = (method, path, status_code)
        self.requests[labels] += 1
        if status_code >= 500:
            self.errors[labels] += 1
        self.latency_seconds_sum += latency_seconds

    def render(self) -> str:
        lines = [
            "# HELP ds_service_up Service liveness gauge.",
            "# TYPE ds_service_up gauge",
            f'ds_service_up{{service="{self.service}"}} 1',
            "# HELP ds_service_uptime_seconds Service uptime in seconds.",
            "# TYPE ds_service_uptime_seconds gauge",
            f'ds_service_uptime_seconds{{service="{self.service}"}} {time.time() - self.started_at:.3f}',
            "# HELP ds_http_requests_total HTTP requests by method, path and status.",
            "# TYPE ds_http_requests_total counter",
        ]
        for (method, path, status_code), count in sorted(self.requests.items()):
            lines.append(
                f'ds_http_requests_total{{service="{self.service}",method="{method}",path="{path}",status="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP ds_http_5xx_total HTTP 5xx responses by method, path and status.",
                "# TYPE ds_http_5xx_total counter",
            ]
        )
        for (method, path, status_code), count in sorted(self.errors.items()):
            lines.append(
                f'ds_http_5xx_total{{service="{self.service}",method="{method}",path="{path}",status="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP ds_http_request_duration_seconds_sum Total observed HTTP request duration.",
                "# TYPE ds_http_request_duration_seconds_sum counter",
                f'ds_http_request_duration_seconds_sum{{service="{self.service}"}} {self.latency_seconds_sum:.6f}',
            ]
        )
        return "\n".join(lines) + "\n"


def install_metrics(app: FastAPI, service: str) -> None:
    metrics = HttpMetrics(service)
    app.state.metrics = metrics

    @app.middleware("http")
    async def collect_http_metrics(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            status_code = response.status_code if response is not None else 500
            path = request.scope.get("route").path if request.scope.get("route") else request.url.path
            metrics.observe(request.method, str(path), status_code, time.perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(metrics.render(), media_type="text/plain; version=0.0.4")
