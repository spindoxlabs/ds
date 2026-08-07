# ds-federated-catalog

A DCAT-AP 3.0 catalog crawler that aggregates dataset offerings from all dataspace participants into a single federated view.

Port: `30003`

> Concepts are published at **<https://spindoxlabs.github.io/ds/>** — see [the overview](https://spindoxlabs.github.io/ds/) for how the pieces fit, [Catalogue and metadata](https://spindoxlabs.github.io/ds/rulebook/catalogue-and-metadata/) for what a catalogue may claim, and [Data exchange](https://spindoxlabs.github.io/ds/rulebook/data-exchange/). This README covers the
> local surface only. Working on the code? Read `AGENTS.md` in this directory.
URL: `http://portal.dataspaces.localhost/api/catalog/`

---

## Purpose

In a multi-participant dataspace, each provider publishes datasets through their own EDC connector. This service periodically crawls all known participant DSP endpoints, caches the resulting DCAT catalogs, and exposes a unified search API.

- Discovers participants from the identity-registry service (`GET /admin/participants`); file-based fallback available
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
| `CATALOG_PARTICIPANTS_YAML` | `/governance/participants.yaml` | Participant registry file path (fallback; only used when `CATALOG_IDENTITY_REGISTRY_URL` is not set) |
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

Entry point: `fc-cli` (defined in `pyproject.toml`, installed as a console script in the
image).

**Read-only, deliberately.** A Typer CLI with two commands:

| Command | Purpose |
|---------|---------|
| `fc-cli crawl` | One-shot crawl of all configured sources (DSP + DCAT), print results |
| `fc-cli status` | Show configured sources and their stats |

### Why there is no `sync`

A `sync` command used to map crawled DCAT-AP datasets into EDC assets, policies and
contract definitions and push them at `POST /provider/sync`. It never worked: that route's
body is `{governance_yaml_path}`, so the payloads were dropped as extra keys and the call
triggered an unrelated sync of the participant's *own* `governance.yaml` — returning 200,
which the CLI reported as `✓` per dataset.

It is removed rather than repaired, because the contract it needed should not exist here.
This data space's recorded catalogue architecture is *distributed catalogues with an
optional federated index*, pull-synchronised (rulebook §1, answering `DSSC-PUB-06`/`-46`).
Publication belongs to the Participant Agent (`DSSC-PUB-12`) and only an authenticated,
authorized data provider may publish its own offering (`DSSC-PUB-13`/`-14`/`-19`). A push
path here would let the index publish a third party's metadata into this participant's EDC
under this participant's contract.

It also could not carry the material required to do so. DCAT-AP supplies the descriptive
half — title, description, keywords, publisher, `dct:temporal`, `dct:conformsTo`, a
distribution `accessURL` — which maps onto `governance.yaml`'s `dcat:` block. It supplies
none of `policy.audience`, `policy.consent`, `policy.purpose`, `dataspace.sharing_offers` or
`dataspace.data_address`, which are decisions of the importing participant rather than facts
of the source catalogue.

An external DCAT-AP catalogue is folded in through the **read** side instead — a
`catalogues.yaml` entry crawled by `crawl_dcat_source`, where the index is advisory
(rulebook `C-2`) and claims no authority over what it republishes.

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
