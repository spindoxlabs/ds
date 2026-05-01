# ds-federated-catalog — Agent Guide

## Service identity

- **Role**: DCAT-AP catalog crawler and aggregator
- **Language**: Python 3.12, FastAPI
- **Port**: 30003 (debug: 30903)
- **URL**: `https://federated-catalog.dataspaces.localhost`
- **Database**: none (in-memory cache)

## Source layout

```
src/federated_catalog/
├── main.py          FastAPI app factory
├── config.py        Pydantic settings (CatalogSettings)
├── crawler.py       DSP catalog fetching logic — calls connector DSP endpoints
├── cache.py         In-memory TTL cache for crawled catalogs
├── registry.py      Participant registry integration (reads participants.yaml)
└── api/
    └── catalog.py   REST endpoints — GET /catalog, GET /catalog/search
```

## Key files for common tasks

| Task | Files to touch |
|------|---------------|
| Change crawl logic or schedule | `crawler.py`, `config.py` (CATALOG_CRAWL_INTERVAL) |
| Modify cache behavior | `cache.py` |
| Add search/filter capabilities | `api/catalog.py` |
| Change participant discovery | `registry.py` |

## Coding conventions

- Crawl runs on a configurable interval (default 300s) with a startup delay (default 15s)
- Uses the connector's participant registry for endpoint discovery
- Catalogs are cached in memory with TTL — no persistent storage
- DCAT-AP 3.0 response format with `application/ld+json` content type

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `CATALOG_CONNECTOR_URL` | `http://ds-connector:30001` | ds-connector URL for catalog proxy |
| `CATALOG_PARTICIPANTS_YAML` | — | Path to participants.yaml |
| `CATALOG_CRAWL_INTERVAL` | `300` | Seconds between crawls |
| `CATALOG_STARTUP_DELAY` | `15` | Seconds before first crawl |
| `CATALOG_BASE_URL` | `https://federated-catalog.dataspaces.localhost` | Public URL for self-references |

## Integration points

- **Upstream**: Portal queries this service for aggregated catalog views
- **Downstream**: reads participant registry, calls connector DSP endpoints for DCAT catalogs
