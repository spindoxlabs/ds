"""OpenTelemetry tracing, correlated by DSP agreement id.

Rulebook [Provenance and logging](../../../docs/rulebook/provenance-and-logging.md)
§5 step 3. What metrics cannot answer: `ds_http_request_duration_seconds` measures
*one hop*, and every operation this platform is judged on spans several —
catalogue fetch, negotiation to agreement, transfer to first row, consent
decision to negotiation resume. Three of those four SLIs are unmeasurable without
this.

## One switch, two languages

**Tracing is on when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, and off when it is
not.** There is no second flag, and that is deliberate: the EDC runs the
OpenTelemetry *Java agent*, which reads the same standard variable, so one value
configures the Python services and the EDCs together. A separate
``DS_TRACING_ENABLED`` would be a second holder of one fact — and the shape of
`T-4`, a setting that has to agree with another setting and eventually does not.

Every other knob is OpenTelemetry's own (``OTEL_TRACES_SAMPLER``,
``OTEL_RESOURCE_ATTRIBUTES``, …), read by the SDK, documented by OpenTelemetry,
and identical on both sides for the same reason.

## Correlation is by attribute, not by parent span

EDC propagates W3C trace context across the consumer–provider hop, so a DSP
exchange *can* be one trace. That is not enough to rely on:

* a counterparty in a real dataspace exports to **its own** backend, and may run
  no tracing at all — a trace that needs both halves to be joinable is a trace
  that works in dev and not in production;
* the interesting questions are asked about an **agreement**, not a request, and
  an agreement outlives the trace that created it. "Show me the transfer that
  used agreement X" is a query about something recorded hours earlier.

So the correlation key is the one `EDCL-06` settled: ``dsp_agreement_id``, the
*shared* id both parties see, not the local ``agreement_id``. It lands on spans
as :data:`AGREEMENT_ID_ATTRIBUTE`.

## Why a span processor and not a call at each site

:func:`correlate_agreement` sets a context variable; :class:`AgreementCorrelator`
stamps it onto **every span started while it is set**. Tagging at each call site
instead would put the attribute on whichever span happened to be current — so a
trace would be findable by agreement id only through the one span that thought to
say so, and a new span added later would silently not be. This repository has
twice fixed a hand-kept list that mirrored something it sat beside (`E2E-03`,
`E2E-14`); a hand-kept set of tagging call sites is the same shape.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI

log = logging.getLogger(__name__)

#: The span attribute every ds service correlates on. Vendor-prefixed because
#: OpenTelemetry's own namespaces are reserved for its semantic conventions, and
#: an attribute that looks standard but is not is worse than an obviously local
#: one.
AGREEMENT_ID_ATTRIBUTE = "ds.dsp.agreement_id"

#: The one variable that turns tracing on, here and in the EDC's Java agent.
ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"

#: Set by :func:`correlate_agreement`, read by :class:`AgreementCorrelator`.
_current_agreement: ContextVar[str | None] = ContextVar(
    "ds_obs_current_agreement", default=None
)

#: Paths whose spans are dropped. A liveness probe every 10s and a scrape every
#: 15s are the same lowest-information, highest-volume traffic
#: `ProbeAccessFilter` already removes from the access log — and in a trace
#: backend they are worse, because they are billed and stored per span.
_PROBE_PATHS = ("/health", "/metrics")

_configured = False


def tracing_endpoint() -> str | None:
    """The configured OTLP endpoint, or ``None`` when tracing is off."""
    raw = os.getenv(ENDPOINT_ENV)
    return raw.strip() or None if raw else None


def correlate_agreement(dsp_agreement_id: str | None) -> None:
    """Attach *dsp_agreement_id* to every span started from here on in this task.

    Takes the **shared** DSP agreement id, never the local one — the whole point
    is that a counterparty's spans carry the same value. Pass ``None`` and nothing
    is stamped, which is the honest outcome for a request that has no agreement
    yet: an attribute whose value is ``"unknown"`` satisfies "the field is
    present" while proving nothing (`PROV-01` made that mistake with a hash).
    """
    _current_agreement.set(dsp_agreement_id or None)


@contextmanager
def agreement_scope(dsp_agreement_id: str | None) -> Iterator[None]:
    """:func:`correlate_agreement` for a bounded block, restoring the previous id.

    For a background worker that handles many agreements on one task — a sweeper,
    a crawl — where leaving the last one set would mis-attribute everything after
    it. A request handler does not need this: each request runs in its own
    context, so the value cannot leak into the next one.
    """
    token = _current_agreement.set(dsp_agreement_id or None)
    try:
        yield
    finally:
        _current_agreement.reset(token)


def current_agreement() -> str | None:
    return _current_agreement.get()


def _build_correlator() -> Any:
    """The span processor, built lazily so the SDK import stays in the extra."""
    from opentelemetry.sdk.trace import SpanProcessor

    class AgreementCorrelator(SpanProcessor):
        """Stamp the in-scope DSP agreement id on every span as it starts.

        ``on_start`` rather than ``on_end``: a span's attributes are readable by
        a sampler and by anything reading the live span, and an attribute added
        at the end is absent for exactly as long as the span is interesting.
        """

        def on_start(self, span: Any, parent_context: Any = None) -> None:
            agreement = _current_agreement.get()
            if agreement:
                span.set_attribute(AGREEMENT_ID_ATTRIBUTE, agreement)

    return AgreementCorrelator()


def configure_tracing(service: str) -> bool:
    """Install the SDK, the OTLP exporter and outbound-HTTP instrumentation.

    Returns whether tracing is on, so a caller can log one line about it rather
    than leaving an operator to infer it from the absence of spans.

    Idempotent: a second call is a no-op, because instrumenting ``httpx`` twice
    wraps the client twice and doubles every outbound span.
    """
    global _configured

    endpoint = tracing_endpoint()
    if endpoint is None:
        # **Said out loud, once.** "No spans are arriving" and "tracing was never
        # switched on" look identical from a backend, and this platform has paid
        # for that distinction more than once.
        log.info(
            "%s: tracing is off — set %s to enable it (the EDC's Java agent "
            "reads the same variable)",
            service,
            ENDPOINT_ENV,
        )
        return False

    if _configured:
        return True

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # `service.name` is what every backend groups by, and it is taken from the
    # argument rather than `OTEL_SERVICE_NAME` — one image runs one service, and
    # a deployment that set the variable once would label all of them the same.
    provider = TracerProvider(
        resource=Resource.create({"service.name": service}),
    )
    provider.add_span_processor(_build_correlator())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()

    _configured = True
    log.info("%s: tracing on — exporting spans to %s", service, endpoint)
    return True


def install_tracing(app: FastAPI, service: str) -> bool:
    """:func:`configure_tracing` plus server spans for *app*.

    Mirrors ``install_metrics``: the FastAPI half is separate so a CLI can trace
    its outbound calls without a web framework.
    """
    if not configure_tracing(service):
        return False

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        # Same two paths `ProbeAccessFilter` drops from the access log, and the
        # instrumentation matches on the raw path, so the templates are these.
        excluded_urls=",".join(_PROBE_PATHS),
        # **Three spans per request become one.** The ASGI layer opens a child
        # span per `http.receive` and `http.send` event, so a plain GET arrived
        # as `GET /x`, `GET /x http send` and `GET /x http send` again. They carry
        # no timing a reader wants — the server span already has the duration —
        # and a trace backend stores and bills every one. Measured on
        # `ds-provenance` before this: 4 requests, 12 spans.
        exclude_spans=["receive", "send"],
    )
    return True
