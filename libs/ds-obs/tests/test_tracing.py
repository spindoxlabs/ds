"""Tracing, and specifically the parts that would fail silently.

A tracing layer is the easiest thing in this repository to ship broken: spans go
to a collector, nobody reads them for a week, and "no spans" is
indistinguishable from "no traffic", "exporter misconfigured" and "never enabled".
So every test here pins something whose failure produces *silence* rather than an
error — which is the defect class this codebase keeps paying for (`CI-02`,
`E2E-01`, `GOV-19`).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from ds_obs import tracing
from ds_obs.tracing import (
    AGREEMENT_ID_ATTRIBUTE,
    ENDPOINT_ENV,
    agreement_scope,
    configure_tracing,
    correlate_agreement,
    current_agreement,
    install_tracing,
    tracing_endpoint,
)


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """`configure_tracing` is idempotent by a module flag; tests must not inherit it."""
    monkeypatch.setattr(tracing, "_configured", False)
    correlate_agreement(None)
    yield
    correlate_agreement(None)


@pytest.fixture
def recorded() -> tuple[TracerProvider, InMemorySpanExporter]:
    """A provider carrying the real correlator and an in-memory exporter.

    The correlator is the unit under test, so it is the real one — a fake would
    assert that the test's copy of the logic works.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(tracing._build_correlator())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


# ── The switch ────────────────────────────────────────────────────────────────
#
# One variable, shared with the EDC's Java agent. A second flag would be a
# second holder of one fact, which is `T-4`.


class TestTheSwitch:
    def test_no_endpoint_means_off(self, monkeypatch):
        monkeypatch.delenv(ENDPOINT_ENV, raising=False)
        assert tracing_endpoint() is None
        assert configure_tracing("svc") is False

    def test_a_blank_endpoint_is_off_not_a_broken_exporter(self, monkeypatch):
        """`OTEL_EXPORTER_OTLP_ENDPOINT=""` is how a chart renders "unset".

        Treated as absent. Passing it through would build an exporter aimed at
        nowhere, which retries, logs, and still produces no spans.
        """
        monkeypatch.setenv(ENDPOINT_ENV, "   ")
        assert tracing_endpoint() is None
        assert configure_tracing("svc") is False

    def test_being_off_is_stated_not_inferred(self, monkeypatch, caplog):
        """"No spans arriving" and "never switched on" must not look identical."""
        monkeypatch.delenv(ENDPOINT_ENV, raising=False)
        with caplog.at_level("INFO"):
            configure_tracing("ds-connector")
        assert any(
            ENDPOINT_ENV in record.getMessage() for record in caplog.records
        ), "a service with tracing off said nothing about it"

    def test_the_endpoint_variable_is_opentelemetry_s_own_name(self):
        """Not a `DS_`-prefixed alias.

        The EDC runs the OpenTelemetry Java agent, which reads this exact name —
        so one value configures both languages. Renaming it here would silently
        decouple the Python services from the EDCs, and the symptom would be a
        trace that stops at the DSP hop.
        """
        assert ENDPOINT_ENV == "OTEL_EXPORTER_OTLP_ENDPOINT"


# ── Correlation ───────────────────────────────────────────────────────────────


class TestAgreementCorrelation:
    def test_every_span_in_scope_carries_the_agreement(self, recorded):
        """The reason this is a span processor and not a call at each site.

        A trace is only findable by agreement id if *its spans* carry it — not
        just the one span whose handler remembered to tag itself.
        """
        provider, exporter = recorded
        tracer = provider.get_tracer(__name__)

        correlate_agreement("dsp-agreement-42")
        with tracer.start_as_current_span("negotiate"):
            with tracer.start_as_current_span("call-pdp"):
                pass

        spans = exporter.get_finished_spans()
        assert {s.name for s in spans} == {"negotiate", "call-pdp"}
        for span in spans:
            assert span.attributes[AGREEMENT_ID_ATTRIBUTE] == "dsp-agreement-42"

    def test_no_agreement_stamps_nothing_rather_than_a_placeholder(self, recorded):
        """`"unknown"` would satisfy "the attribute is present" and prove nothing.

        `PROV-01` is the same mistake with a hash: a typed field accepting
        `"pending"` reads as recorded when it is not.
        """
        provider, exporter = recorded
        tracer = provider.get_tracer(__name__)

        correlate_agreement(None)
        with tracer.start_as_current_span("no-agreement-yet"):
            pass

        span = exporter.get_finished_spans()[0]
        assert AGREEMENT_ID_ATTRIBUTE not in (span.attributes or {})

    def test_an_empty_string_is_treated_as_absent(self, recorded):
        provider, exporter = recorded
        tracer = provider.get_tracer(__name__)

        correlate_agreement("")
        with tracer.start_as_current_span("blank"):
            pass

        span = exporter.get_finished_spans()[0]
        assert AGREEMENT_ID_ATTRIBUTE not in (span.attributes or {})

    def test_a_scope_restores_the_previous_agreement(self, recorded):
        """A worker handling many agreements on one task must not leak the last one.

        Without this, everything a sweeper does after its first agreement is
        attributed to that agreement — which is worse than no attribute, because
        it is confidently wrong.
        """
        provider, exporter = recorded
        tracer = provider.get_tracer(__name__)

        correlate_agreement("outer")
        with agreement_scope("inner"):
            with tracer.start_as_current_span("inside"):
                pass
            assert current_agreement() == "inner"
        with tracer.start_as_current_span("after"):
            pass

        by_name = {s.name: s for s in exporter.get_finished_spans()}
        assert by_name["inside"].attributes[AGREEMENT_ID_ATTRIBUTE] == "inner"
        assert by_name["after"].attributes[AGREEMENT_ID_ATTRIBUTE] == "outer"

    def test_the_scope_restores_even_when_the_body_raises(self, recorded):
        correlate_agreement("outer")
        with pytest.raises(RuntimeError):
            with agreement_scope("inner"):
                raise RuntimeError("boom")
        assert current_agreement() == "outer"

    def test_the_attribute_is_not_in_an_opentelemetry_namespace(self):
        """A local attribute that looks standard is worse than one that does not.

        OpenTelemetry reserves its own namespaces for semantic conventions; a
        future convention taking this name would silently change its meaning.
        """
        assert AGREEMENT_ID_ATTRIBUTE.startswith("ds.")


# ── The FastAPI half ──────────────────────────────────────────────────────────


class TestInstallTracing:
    async def test_off_installs_nothing_and_the_app_still_serves(self, monkeypatch):
        """Tracing being off must not be able to break a request path."""
        monkeypatch.delenv(ENDPOINT_ENV, raising=False)
        app = FastAPI()

        @app.get("/x")
        async def x() -> dict[str, bool]:
            return {"ok": True}

        assert install_tracing(app, "svc") is False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await client.get("/x")).status_code == 200

    def test_probe_paths_are_excluded(self):
        """`/health` and `/metrics` are the same traffic `ProbeAccessFilter` drops.

        In a trace backend they are worse than noise: a probe every 10s and a
        scrape every 15s are stored and billed per span, and they would outnumber
        every real exchange.
        """
        from ds_obs.logging import _PROBE_PATHS as log_probes

        assert tracing._PROBE_PATHS == log_probes, (
            "the traced and logged probe-path lists have drifted apart — one list, "
            "one meaning, or a path gets suppressed in one place and not the other"
        )


def test_the_asgi_send_and_receive_spans_are_excluded():
    """One span per request, not three.

    The ASGI layer opens a child span per `http.receive` and `http.send` event.
    They duplicate the server span's timing and carry nothing else, and a trace
    backend stores and bills each one — measured on `ds-provenance`: 4 requests
    produced 12 spans. Asserted against the call, because the symptom is a bill
    and a cluttered waterfall rather than a failure.
    """
    import inspect

    source = inspect.getsource(install_tracing)
    assert 'exclude_spans=["receive", "send"]' in source
