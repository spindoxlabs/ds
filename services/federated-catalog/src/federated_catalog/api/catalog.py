"""Federated catalog API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/catalog", tags=["catalog"])

JSONLD_MEDIA_TYPE = "application/ld+json"


def _jsonld(data: dict, base_url: str) -> JSONResponse:
    wrapper = {
        "@context": f"{base_url}/catalog/context",
        **data,
    }
    return JSONResponse(content=wrapper, media_type=JSONLD_MEDIA_TYPE)


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
            "hydra:totalItems": len(datasets),
            "hydra:offset": offset,
            "hydra:limit": limit,
        },
        settings.base_url,
    )


@router.get("/context")
async def get_context(request: Request):
    """JSON-LD context document."""
    settings = request.app.state.settings
    context = {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "odrl": "http://www.w3.org/ns/odrl/2/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "ds": "https://dataspaces.localhost/ns/energy#",
            "hydra": "http://www.w3.org/ns/hydra/core#",
            "dcat:dataset": {"@container": "@set"},
            "dct:publisher": {"@type": "@id"},
        }
    }
    return JSONResponse(content=context, media_type=JSONLD_MEDIA_TYPE)


@router.get("/meta")
async def get_meta(request: Request):
    """Crawl health, provider list, and dataset counts."""
    cache = request.app.state.cache
    return cache.meta


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
            "hydra:totalItems": len(results),
            "hydra:offset": body.offset,
            "hydra:limit": body.limit,
        },
        settings.base_url,
    )
