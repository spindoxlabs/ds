# ds-federated-catalog

A DCAT-AP 3.0 catalog crawler that aggregates dataset offerings from all dataspace participants into a single federated view.

Port: `30003`
URL: `https://federated-catalog.dataspaces.localhost`

---

## Purpose

In a multi-participant dataspace, each provider publishes datasets through their own EDC connector. This service periodically crawls all known participant DSP endpoints, caches the resulting DCAT catalogs, and exposes a unified search API.

- Discovers participants from `participants.yaml` (shared with ds-connector)
- Crawls DCAT catalogs on a configurable interval (default: every 5 minutes)
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
| `CATALOG_CRAWL_INTERVAL` | `300` | Seconds between crawl cycles |
| `CATALOG_STARTUP_DELAY` | `15` | Seconds before first crawl after boot |
| `CATALOG_BASE_URL` | `https://federated-catalog.dataspaces.localhost` | Public URL for self-references |

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
