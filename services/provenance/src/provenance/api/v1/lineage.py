"""Lineage traversal and complex query routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_settings_dep
from ...schemas.context import JSONLDResponse
from ...services.lineage_service import get_lineage
from ...services.jsonld_service import lineage_to_jsonld

router = APIRouter()


@router.get("/lineage/{iri:path}")
async def get_lineage_route(
    iri: str,
    direction: str = Query(default="both", pattern="^(upstream|downstream|both)$"),
    max_depth: int = Query(default=5, ge=1, le=20),
    relation_types: str | None = Query(default=None, description="Comma-separated list"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    rtype_list = [r.strip() for r in relation_types.split(",")] if relation_types else None

    graph_data = await get_lineage(
        db, iri,
        direction=direction,
        max_depth=min(max_depth, settings.max_lineage_depth),
        relation_types=rtype_list,
    )

    if not graph_data.nodes:
        raise HTTPException(404, f"No node found with IRI: {iri}")

    response_body = {
        "@context": settings.context_url,
        "root": iri,
        "direction": direction,
        "depth": max(graph_data.depth_map.values(), default=0),
        "@graph": lineage_to_jsonld(graph_data),
    }
    from fastapi.responses import JSONResponse
    return JSONResponse(content=response_body, media_type="application/ld+json")
