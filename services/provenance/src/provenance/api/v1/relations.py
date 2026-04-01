"""PROV-O relations (edges) routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_settings_dep
from ...schemas.context import JSONLDResponse
from ...schemas.prov import RelationCreate
from ...services import relation_service

router = APIRouter()


@router.post("/relations", status_code=201)
async def create_relation(
    data: RelationCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    async with db.begin():
        try:
            relation, created = await relation_service.create_relation(db, data)
        except ValueError as e:
            raise HTTPException(422, str(e))

    status_code = 201 if created else 409
    graph = [{
        "@id": f"urn:relation:{relation.id}",
        "@type": f"prov:{relation.relation_type}",
        "prov:subject": data.subject_iri,
        "prov:object": data.object_iri,
    }]
    return JSONLDResponse(graph, settings.context_url, status_code=status_code)
