"""Each test here corresponds to a defect measured on a running service."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ds_obs.metrics import UNMATCHED, HttpMetrics, install_metrics


def _series(rendered: str, prefix: str) -> list[str]:
    return [ln for ln in rendered.splitlines() if ln.startswith(prefix)]


class TestHistogram:
    """The old metric was a bare `_sum`: no count, no buckets, no path label."""

    def test_buckets_are_cumulative_and_carry_inf(self):
        m = HttpMetrics("svc", buckets=(0.01, 0.1, 1.0))
        for latency in (0.005, 0.05, 0.5, 5.0):
            m.observe("GET", "/x", 200, latency)
        rendered = m.render()

        got = {}
        for line in _series(rendered, "ds_http_request_duration_seconds_bucket"):
            le = line.split('le="', 1)[1].split('"', 1)[0]
            got[le] = int(line.rsplit(" ", 1)[1])

        # Cumulative: each bound counts everything at or below it.
        assert got == {"0.01": 1, "0.1": 2, "1": 3, "+Inf": 4}

    def test_sum_and_count_are_both_emitted(self):
        """Without `_count` there is no average, and `_sum` alone was all there was."""
        m = HttpMetrics("svc")
        m.observe("GET", "/x", 200, 0.25)
        m.observe("GET", "/x", 200, 0.75)
        rendered = m.render()

        assert (
            'ds_http_request_duration_seconds_count'
            '{service="svc",method="GET",path="/x"} 2'
        ) in rendered
        sum_line = _series(rendered, "ds_http_request_duration_seconds_sum")[0]
        assert float(sum_line.rsplit(" ", 1)[1]) == pytest.approx(1.0)

    def test_latency_is_labelled_by_path(self):
        """The old sum had no path label, so health checks and crawls averaged.

        Measured live before this: 164 of ~200 requests on a running service were
        `/health`, so the single latency number described the liveness probe.
        """
        m = HttpMetrics("svc")
        m.observe("GET", "/health", 200, 0.001)
        m.observe("GET", "/catalog", 200, 2.0)
        rendered = m.render()

        counts = {
            line.split('path="', 1)[1].split('"', 1)[0]: float(line.rsplit(" ", 1)[1])
            for line in _series(rendered, "ds_http_request_duration_seconds_sum")
        }
        assert counts["/health"] == pytest.approx(0.001)
        assert counts["/catalog"] == pytest.approx(2.0)

    def test_declares_itself_a_histogram(self):
        """`histogram_quantile` refuses anything not typed as one."""
        assert (
            "# TYPE ds_http_request_duration_seconds histogram"
            in HttpMetrics("svc").render()
        )


class TestRedundantSeriesRemoved:
    def test_no_5xx_family(self):
        """`ds_http_requests_total{status=~"5.."}` is the same data.

        It was also empty whenever the service was healthy, which on a dashboard
        reads as a broken query rather than as no errors.
        """
        m = HttpMetrics("svc")
        m.observe("GET", "/x", 500, 0.01)
        assert "ds_http_5xx_total" not in m.render()

    def test_errors_are_still_countable_from_requests_total(self):
        m = HttpMetrics("svc")
        m.observe("GET", "/x", 500, 0.01)
        assert 'path="/x",status="500"} 1' in m.render()


class TestCardinality:
    """Verified live: four curls at bogus URLs minted four permanent series."""

    @pytest.mark.asyncio
    async def test_unmatched_routes_collapse_to_one_label(self):
        app = FastAPI()

        @app.get("/known")
        async def known():
            return {}

        install_metrics(app, "svc")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as ac:
            for path in ("/nope-aaa", "/nope-bbb", "/wp-admin/x", "/.env"):
                await ac.get(path)
            await ac.get("/known")

        rendered = app.state.metrics.render()
        paths = {
            line.split('path="', 1)[1].split('"', 1)[0]
            for line in _series(rendered, "ds_http_requests_total")
        }
        assert paths == {UNMATCHED, "/known"}
        assert f'path="{UNMATCHED}",status="404"}} 4' in rendered

    @pytest.mark.asyncio
    async def test_a_matched_route_reports_its_template_not_its_arguments(self):
        """A templated path is bounded by the route table; a raw URL is not."""
        app = FastAPI()

        @app.get("/catalog/{iri:path}")
        async def one(iri: str):
            return {}

        install_metrics(app, "svc")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as ac:
            for i in range(5):
                await ac.get(f"/catalog/dataset-{i}")

        rendered = app.state.metrics.render()
        assert 'path="/catalog/{iri:path}",status="200"} 5' in rendered
        assert "dataset-0" not in rendered


class TestEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_serves_the_prometheus_content_type(self):
        app = FastAPI()
        install_metrics(app, "svc")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as ac:
            r = await ac.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert 'ds_service_up{service="svc"} 1' in r.text

    @pytest.mark.asyncio
    async def test_a_failing_handler_is_still_observed(self):
        """The `finally` is what makes an unhandled exception countable."""
        app = FastAPI()

        @app.get("/boom")
        async def boom():
            raise RuntimeError("boom")

        install_metrics(app, "svc")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as ac:
            with pytest.raises(RuntimeError):
                await ac.get("/boom")

        assert 'status="500"' in app.state.metrics.render()
