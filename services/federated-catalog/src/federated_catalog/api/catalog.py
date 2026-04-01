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
    """Return a single dataset by IRI."""
    cache = request.app.state.cache
    settings = request.app.state.settings
    # Reconstruct IRI (path param strips leading slash for http:// IRIs)
    if not dataset_iri.startswith("http"):
        dataset_iri = "https://" + dataset_iri
    ds = cache.get_by_iri(dataset_iri)
    if ds is None:
        raise HTTPException(404, f"Dataset {dataset_iri!r} not found in catalog")
    return _jsonld({"@type": "dcat:Dataset", **ds}, settings.base_url)


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
