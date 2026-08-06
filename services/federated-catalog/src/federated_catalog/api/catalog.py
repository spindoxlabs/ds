"""Federated catalog API endpoints."""
from __future__ import annotations

from urllib.parse import quote

from ds.governance.dcat import to_catalog_record, to_data_service
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/catalog", tags=["catalog"])

#: `GET /catalog/context` is mounted here instead of on `router`, and this
#: router is included **without** the read guard. Every response this service
#: returns advertises the context as its `@context`, so a JSON-LD processor
#: dereferences it as a matter of course — holding no token, because it is a
#: parser and not a participant. Guarding it made every one of our own documents
#: unprocessable while protecting nothing: the document is a fixed list of
#: vocabulary prefixes, identical for every caller, and discloses no dataset,
#: participant or offer.
public_router = APIRouter(prefix="/catalog", tags=["catalog"])

JSONLD_MEDIA_TYPE = "application/ld+json"


def _jsonld(data: dict, base_url: str) -> JSONResponse:
    wrapper = {
        "@context": f"{base_url}/catalog/context",
        **data,
    }
    return JSONResponse(content=wrapper, media_type=JSONLD_MEDIA_TYPE)


def _records(page: list[dict], cache, base_url: str) -> list[dict]:
    """A `dcat:CatalogRecord` per entry on the page (`DSSC-PUB-45`, `C-8`).

    The record carries what *this* catalogue knows about the entry and the
    provider does not: when the crawl last saw it, and which source it came
    from. `dcat:dataset` stays alongside — see the note in
    :func:`ds.governance.dcat.to_catalog_record`'s module docstring.
    """
    modified = cache.last_crawl_iso
    root = base_url.rstrip("/")
    records = []
    for ds in page:
        iri = ds.get("@id") or ds.get("id")
        if not iri:
            continue
        records.append(
            to_catalog_record(
                dataset_id=iri,
                record_id=f"{root}/catalog/record/{quote(iri, safe='')}",
                modified=modified,
                source=cache.source_of(iri),
            )
        )
    return records


def _services(cache, base_url: str) -> list[dict]:
    """A `dcat:DataService` per crawled source (`DSSC-PUB-41`, `C-7`).

    The index does not serve these datasets — it republishes descriptions of
    them — so the endpoint a consumer needs is the source's, not ours. A source
    that published nothing this cycle still gets a service entry: the endpoint is
    a fact about the participant, not about how many datasets it happened to
    offer.
    """
    ids_by_source = cache.dataset_ids_by_source()
    root = base_url.rstrip("/")
    return [
        to_data_service(
            service_id=f"{root}/catalog/service/{quote(source_id, safe='')}",
            title=f"{source_id} data service",
            endpoint_url=endpoint.url,
            serves_dataset=ids_by_source.get(source_id) or None,
            conforms_to=endpoint.conforms_to,
        )
        for source_id, endpoint in cache.endpoints().items()
        if endpoint.url
    ]


@router.get("")
async def get_catalog(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return all cached datasets as a dcat:Catalog."""
    cache = request.app.state.cache
    settings = request.app.state.settings
    datasets = cache.all_datasets()
    page = datasets[offset : offset + limit]
    return _jsonld(
        {
            "@type": "dcat:Catalog",
            "dct:title": "Dataspaces Federated Catalog",
            "dcat:dataset": page,
            "dcat:record": _records(page, cache, settings.base_url),
            "dcat:service": _services(cache, settings.base_url),
            "hydra:totalItems": len(datasets),
            "hydra:offset": offset,
            "hydra:limit": limit,
        },
        settings.base_url,
    )


@public_router.get("/context")
async def get_context():
    """JSON-LD context document."""
    context = {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "odrl": "http://www.w3.org/ns/odrl/2/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "foaf": "http://xmlns.com/foaf/0.1/",
            "ds": "https://dataspaces.localhost/ns/energy#",
            "hydra": "http://www.w3.org/ns/hydra/core#",
            "dcat:dataset": {"@container": "@set"},
            "dcat:record": {"@container": "@set"},
            "dcat:service": {"@container": "@set"},
            "dct:publisher": {"@type": "@id"},
        }
    }
    return JSONResponse(content=context, media_type=JSONLD_MEDIA_TYPE)


@router.get("/meta")
async def get_meta(request: Request):
    """Crawl health, provider list, dataset counts, and how often it refreshes.

    `crawl_interval_seconds` is served because *how stale can this be?* is a
    question every reader of an advisory index has, and until now the only way
    to answer it was to read this service's configuration. A caller that has to
    hold its own copy of the number holds a second copy that drifts — and one
    such caller is `ds-e2e --flow catalog-discovery`, whose verdict used to
    depend on where a 300s boundary happened to fall relative to the run
    (`E2E-12`). It waits this interval out instead, derived from here.
    """
    cache = request.app.state.cache
    settings = request.app.state.settings
    return {**cache.meta, "crawl_interval_seconds": settings.crawl_interval}


@router.get("/{dataset_iri:path}")
async def get_dataset(dataset_iri: str, request: Request):
    """Return a single dataset by the IRI the catalogue advertises.

    A dataset IRI is not necessarily a URL. Ours are governance keys —
    ``datasets.silver.meters_15m`` — so unconditionally prefixing ``https://``
    turned every lookup into a miss, and made ``/catalog/datasets`` report
    ``Dataset 'https://datasets' not found``.

    The prefixing exists for a real case, though: a URL IRI arrives here with
    its scheme separator mangled, because the path parameter eats the leading
    slash. So try the value as advertised first, then the repaired-URL forms.
    """
    cache = request.app.state.cache
    settings = request.app.state.settings

    for candidate in _iri_candidates(dataset_iri):
        ds = cache.get_by_iri(candidate)
        if ds is not None:
            # The `@type` override goes *after* the spread. Written before it,
            # the cached document's own bare `Dataset` silently won, so a
            # resolved dataset was typed differently from the same dataset in
            # the catalogue listing.
            return _jsonld({**ds, "@type": "dcat:Dataset"}, settings.base_url)

    raise HTTPException(404, f"Dataset {dataset_iri!r} not found in catalog")


def _iri_candidates(dataset_iri: str) -> list[str]:
    """The forms this path could have meant, most literal first."""
    candidates = [dataset_iri]
    # `https:/host/x` — the path param collapsed the `//` of a URL IRI.
    if dataset_iri.startswith(("http:/", "https:/")) and "://" not in dataset_iri:
        candidates.append(dataset_iri.replace(":/", "://", 1))
    elif not dataset_iri.startswith("http"):
        candidates.append("https://" + dataset_iri)
    return candidates


class SearchRequest(BaseModel):
    q: str | None = None
    access_level: str | None = None
    provider: str | None = None
    keywords: list[str] | None = None
    limit: int = 50
    offset: int = 0


@router.post("/search")
async def search_catalog(body: SearchRequest, request: Request):
    """Filtered search over the cached catalog."""
    cache = request.app.state.cache
    settings = request.app.state.settings
    results = cache.search(
        q=body.q,
        access_level=body.access_level,
        provider=body.provider,
        keywords=body.keywords,
    )
    page = results[body.offset : body.offset + body.limit]
    return _jsonld(
        {
            "@type": "dcat:Catalog",
            "dcat:dataset": page,
            "dcat:record": _records(page, cache, settings.base_url),
            "dcat:service": _services(cache, settings.base_url),
            "hydra:totalItems": len(results),
            "hydra:offset": body.offset,
            "hydra:limit": body.limit,
        },
        settings.base_url,
    )
