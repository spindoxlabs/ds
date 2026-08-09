# ds-obs

Logging configuration, HTTP metrics and tracing, shared by every Python service. Things every
deployable unit needs identically, and which were previously either **missing entirely**
(logging, tracing) or **duplicated four times** (metrics).

No runtime dependencies in the base package. `install_metrics` needs the `fastapi` extra and
`install_tracing` needs `fastapi` plus `tracing`; `configure_logging` needs neither, so a CLI
can use it without pulling a web framework or an OTLP exporter in.

## References

| | |
|---|---|
| Requirements | [DSSC · Publication, Traceability and Observability](../../docs/blueprints/dssc/governance-enablers/publication-traceability-observability.md) — `PTO-03`, `-42`–`-46` |
| Rules | [Rulebook · Provenance and logging](../../docs/rulebook/provenance-and-logging.md) §5, which tracks the observability gap this narrows |

## Where to work

| Task | Start at |
|---|---|
| Log level, format, filters | `logging.py` |
| A new metric, or a label | `metrics.py` |
| Spans, the exporter, correlation | `tracing.py` |

## Rules that are not visible from the code

- **`configure_logging` goes first in the application factory**, before anything that logs.
  It replaces the root logger's handlers, so anything that logged during import already
  wrote through the old configuration.
- **The three env vars are read here, not in a service's `Settings`.** Logging is a property
  of the process, not of the domain. A `CONNECTOR_LOG_LEVEL` would be one more thing that
  can differ between services for no reason. They are `DS_LOG_LEVEL`, `DS_LOG_FORMAT`,
  `DS_LOG_ACCESS_HEALTH`; the chart renders all three from `global.logging` through
  `ds.env.common`, so a deployment sets them **once**.
- **A path label is a route template or `UNMATCHED`, never a URL.** The template is bounded
  by the route table; a raw URL is bounded by whatever anyone types. The version this
  replaces fell back to `request.url.path` on an unmatched route, which meant a vulnerability
  scanner minted one permanent Prometheus series per URL it tried. Measured before the fix:
  four curls at bogus paths, four new series.
- **A latency metric must be a histogram.** The version this replaces exported a bare
  `..._sum` with no `_count` and no path label, so no quantile was derivable and the one
  number it did give was dominated by the liveness probe — on a live service, 164 of ~200
  requests were `/health`. `PR-18`'s SLO row is unachievable without buckets.
- **The registry is in-process, and that is only correct at `--workers 1`**, which every
  Dockerfile pins. More workers means each holds its own counters and a scrape returns
  whichever answered. That needs a shared store, not a bigger worker count.
- **`ProbeAccessFilter` keeps a line whenever it is unsure.** A filter that guesses wrong
  should add noise, never remove signal — so a non-2xx probe, or an access record whose
  shape is not uvicorn's, is always emitted.

### Tracing

- **`OTEL_EXPORTER_OTLP_ENDPOINT` is the only switch, and it is not a `DS_` name by
  design.** The EDCs read the same variable through the OpenTelemetry Java agent
  (`services/edc-connector/entrypoint.sh`), so one value covers the Python services and the
  DSP hop between two participants' EDCs — and cannot cover half of it. Adding a
  `DS_TRACING_ENABLED` beside it would be a second holder of one fact; the failure it
  produces is a trace that stops at the DSP hop with nothing saying why.
- **Correlate with `correlate_agreement`, never by tagging a span by hand.** It sets a
  context variable and a span processor stamps `ds.dsp.agreement_id` on **every** span
  started while it is set. Tagging at call sites puts the attribute on whichever span happens
  to be current, so a span added later is silently unlabelled — the hand-kept-list shape
  `E2E-03` and `E2E-14` both fixed.
- **Always the *shared* `dsp_agreement_id`, never the local `agreement_id`** (`EDCL-06`).
  The counterparty holds a different value for the local one, so correlating on it produces
  two backends whose spans have nothing in common and no error anywhere.
- **No SQLAlchemy instrumentation, and that is a decision.** It would need the ORM as a
  dependency here, and it hooks engine *creation* — `connector.db.engine` builds its engine
  at import, before any app factory runs. Installing it would give a working import, no
  spans, and nothing saying so. DB spans want the engine passed in, per service.

## Adding it to a service

1. `pyproject.toml`: `"ds-obs"` in `[project].dependencies`, and
   `ds-obs = { path = "../../libs/ds-obs", editable = true }` under `[tool.uv.sources]`.
2. `Dockerfile`: `COPY libs/ds-obs/ /build/ds-obs/` and add `/build/ds-obs` to the by-path
   `uv pip install` beside the other libs.
3. `main.py`: `configure_logging("<service>")` as the first statement of the app factory,
   then `install_metrics(app, "<service>")` if the service's chart opens a scrape path, then
   `install_tracing(app, "<service>")`.

For tracing the dependency is `"ds-obs[tracing]"` in `[project].dependencies` **and**
`'/build/ds-obs[tracing]'` in the Dockerfile's by-path install — the extra is not implied by
the path, so getting only one of the two produces an image whose `install_tracing` raises on
an import a unit test never reaches.

**Both halves in the same change, or neither.** An endpoint whose chart opens no scrape path
is a target Prometheus is refused by default-deny, and the operator's only signal is a metric
that never appears — that is how `ds-provenance` sat, and `ds-identity-registry` was the
inverse until 2026-08-07: no endpoint at all, so the one component every participant depends
on for identity was the only one nothing could observe. **All five services now serve
`/metrics` and all five charts carry `metricsFromPrometheus`.**

Adding one is not new exposure. `/metrics` is in **no chart's Ingress**, default-deny applies,
and the policy admits the monitoring namespace alone — gated on `global.monitoring.serviceMonitor`,
false by default. It stays unauthenticated deliberately: a scraper holds no Keycloak token, so
a bearer guard would replace a working control with a broken one. See
[the rulebook's step 1](../../docs/rulebook/provenance-and-logging.md) and decision `D-2`.

## Testing

`task -d libs/ds-obs test|lint`. Every test corresponds to a defect measured on a running
service — see the docstrings.
