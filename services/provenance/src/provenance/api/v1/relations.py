"""PROV-O relations (edges) routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_settings_dep
from ...schemas.context import JSONLDResponse
from ...schemas.prov import RelationCreate
from ...services import relation_service
from ...services.jsonld_service import relation_to_jsonld

router = APIRouter()


@router.post(
    "/relations",
    status_code=201,
    responses={
        # The route has always answered 409 for a duplicate edge and advertised
        # 201 only, so a generated client had no branch for the commonest
        # non-error outcome — re-posting an edge the ingest path already wrote.
        409: {"description": "The edge already exists; the existing one is returned"},
        422: {"description": "Unknown relation type, or an IRI naming no node"},
    },
)
async def create_relation(
    data: RelationCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    async with db.begin():
        try:
            relation, created, nodes = await relation_service.create_relation(db, data)
        except ValueError as e:
            raise HTTPException(422, str(e))

    status_code = 201 if created else 409
    # Serialised by the same function the lineage graph uses, so an edge does not
    # change shape depending on which route returned it. This used to emit
    # `prov:subject` / `prov:object`, terms `PROV_CONTEXT` does not define.
    graph = [relation_to_jsonld(relation, nodes)]
    return JSONLDResponse(graph, settings.context_url, status_code=status_code)
