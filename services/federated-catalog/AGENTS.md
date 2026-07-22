# ds-federated-catalog — Agent Guide

## Service identity

- **Role**: DCAT-AP catalog crawler and aggregator
- **Language**: Python 3.12, FastAPI
- **Port**: 30003 (debug: 30903)
- **URL**: `http://portal.dataspaces.localhost:9010/api/catalog/` (via Caddy), direct `http://172.17.0.1:30003`
- **Database**: none (in-memory cache)

## Source layout

```
src/federated_catalog/
├── main.py          FastAPI app factory
├── config.py        Pydantic settings (CatalogSettings)
├── crawler.py       DSP catalog fetching logic — calls connector DSP endpoints
├── cache.py         In-memory TTL cache for crawled catalogs
├── registry.py      Participant registry integration (reads from identity-registry API; file-based fallback)
└── api/
    └── catalog.py   REST endpoints — GET /catalog, POST /catalog/search
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
| `CATALOG_CONNECTOR_URL` | `http://172.17.0.1:31001` | ds-connector URL for catalog proxy |
| `CATALOG_IDENTITY_REGISTRY_URL` | `http://identity-registry:30005` | Identity registry URL for participant discovery |
| `CATALOG_CRAWL_INTERVAL` | `300` | Seconds between crawls |
| `CATALOG_STARTUP_DELAY` | `10` | Seconds before first crawl |
| `CATALOG_BASE_URL` | `https://federated-catalog.dataspaces.localhost` | Public URL for self-references |

## Integration points

- **Upstream**: Portal queries this service for aggregated catalog views
- **Downstream**: calls identity-registry `/participants` for provider discovery, calls connector DSP endpoints for DCAT catalogs
