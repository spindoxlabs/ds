# ds-federated-catalog

A DCAT-AP 3.0 catalog crawler that aggregates dataset offerings from all dataspace participants into a single federated view.

Port: `30003`
URL: `https://federated-catalog.dataspaces.localhost`

---

## Purpose

In a multi-participant dataspace, each provider publishes datasets through their own EDC connector. This service periodically crawls all known participant DSP endpoints, caches the resulting DCAT catalogs, and exposes a unified search API.

- Discovers participants from `participants.yaml` (shared with ds-connector)
- Crawls DCAT catalogs on a configurable interval (default: every 5 minutes)
- Crawls external DCAT-AP catalogues directly (plain HTTP GET)
- Caches results in memory with TTL — no persistent storage required
- Returns DCAT-AP 3.0 responses with `application/ld+json` content type

---

## API

### Catalog

- `GET /catalog` — aggregated federated catalog (all participants)
- `GET /catalog/search?q=<query>` — full-text search across cached catalogs
- `GET /health` — liveness check

---

## Configuration

All settings use `pydantic-settings` with sensible defaults for local development.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CATALOG_CONNECTOR_URL` | `http://ds-connector:30001` | ds-connector internal URL |
| `CATALOG_PARTICIPANTS_YAML` | `/governance/participants.yaml` | Participant registry file path |
| `CATALOG_DCAT_SOURCES_YAML` | `""` (empty) | Path to `catalogues.yaml` — external DCAT-AP sources (schema: `schemas/catalogues.schema.json`) |
| `CATALOG_CRAWL_INTERVAL` | `300` | Seconds between crawl cycles |
| `CATALOG_STARTUP_DELAY` | `10` | Seconds before first crawl after boot |
| `CATALOG_MAX_DATASETS_PER_PROVIDER` | `500` | Maximum datasets cached per source (prevents memory bloat) |
| `CATALOG_BASE_URL` | `https://federated-catalog.dataspaces.localhost` | Public URL for self-references |

---

## DCAT sources

Besides crawling DSP providers via the connector, the catalog can crawl external DCAT-AP catalogues directly. This allows federating datasets from portals that expose standard DCAT endpoints but are not dataspace participants.

- `DcatSource` dataclass in `registry.py` is parsed from `catalogues.yaml`
- `crawl_dcat_source(source, max_datasets)` in `crawler.py` does a plain `GET` with `Accept: application/ld+json`
- `crawl_all()` crawls both DSP providers and DCAT sources concurrently via `asyncio.gather`
- Fail-safe: HTTP errors are logged, the source is skipped, and previously-cached entries are retained

---

## CLI (fc-cli)

Entry point: `fc-cli` (defined in `pyproject.toml`).

A Typer CLI with three commands:

| Command | Purpose |
|---------|---------|
| `fc-cli sync --sources <path>` | Crawl DCAT sources, map datasets to EDC payloads, register via `POST /provider/sync` |
| `fc-cli crawl` | One-shot crawl of all configured sources (DSP + DCAT), print results |
| `fc-cli status` | Show configured sources and their stats |

### DCAT-to-EDC mapper

`cli/mapper.py` provides `dcat_to_edc_payloads(dataset, source_defaults)` with two mapping paths:

1. **ODRL pass-through** — extracts `odrl:hasPolicy` from the DCAT distribution and converts the Offer to a Set
2. **Governance-override-based** — builds an ODRL Set from `catalogues.yaml` defaults (`access_requirements`, `consent_required`, `retention_days`)

The mapper builds EDC Asset + PolicyDefinition + ContractDefinition payloads. Datasets with `access_level=secret` are skipped.

---

## Local development

```bash
# Prerequisites: shared infra + ds-connector must be running
docker compose up -d                    # root: caddy + postgres
docker compose -f services/connector/docker-compose.yml up -d

# Install deps and run locally
cd services/federated-catalog
task setup
task run     # http://localhost:30003
```

---

## Docker

```bash
docker compose -f services/connector/docker-compose.yml up -d
# ds-federated-catalog is included in the connector stack
```

The service is declared in `services/connector/docker-compose.yml` alongside the connector stack, since it depends on the connector for participant registry data.

---

## DSSC Blueprint alignment

Implements aspects of:

- **BB04** (Data Offerings & Descriptions) — DCAT-AP 3.0 metadata aggregation
- **BB05** (Publication & Discovery) — federated catalog pattern with periodic crawling
