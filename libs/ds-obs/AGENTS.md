# ds-obs

Logging configuration and HTTP metrics, shared by every Python service. Two things every
deployable unit needs identically, and which were previously either **missing entirely**
(logging) or **duplicated four times** (metrics).

No runtime dependencies. `install_metrics` needs the `fastapi` extra; `configure_logging`
does not, so a CLI can use it without pulling a web framework in.

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

## Adding it to a service

1. `pyproject.toml`: `"ds-obs"` in `[project].dependencies`, and
   `ds-obs = { path = "../../libs/ds-obs", editable = true }` under `[tool.uv.sources]`.
2. `Dockerfile`: `COPY libs/ds-obs/ /build/ds-obs/` and add `/build/ds-obs` to the by-path
   `uv pip install` beside the other libs.
3. `main.py`: `configure_logging("<service>")` as the first statement of the app factory,
   then `install_metrics(app, "<service>")` if the service's chart opens a scrape path.

`ds-identity-registry` takes logging and **not** metrics: its chart mounts no
`metricsFromPrometheus` and it serves no `/metrics`. Adding one would be new exposure, not
de-duplication.

## Testing

`task -d libs/ds-obs test|lint`. Every test corresponds to a defect measured on a running
service — see the docstrings.
