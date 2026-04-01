"""Entities, Activities, Agents CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import get_db, get_settings_dep
from ...schemas.context import JSONLDResponse
from ...schemas.prov import (
    ActivityCreate, AgentCreate, EntityCreate, NodeRead,
)
from ...services import prov_service
from ...services.jsonld_service import node_to_jsonld

router = APIRouter()


def _context_url(settings: Settings) -> str:
    return settings.context_url


# ── Entities ──────────────────────────────────────────────────────────────────

@router.post("/entities", status_code=201)
async def create_entity(
    data: EntityCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    async with db.begin():
        node = await prov_service.create_entity(db, data)
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings), status_code=201)


@router.get("/entities")
async def list_entities(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    nodes = await prov_service.list_nodes(db, node_type="Entity", limit=limit, offset=offset)
    return JSONLDResponse([node_to_jsonld(n) for n in nodes], _context_url(settings))


@router.get("/entities/{iri:path}")
async def get_entity(
    iri: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    node = await prov_service.get_node_by_iri(db, iri)
    if not node or node.node_type != "Entity":
        raise HTTPException(404, "Entity not found")
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings))


@router.delete("/entities/{iri:path}", status_code=204)
async def delete_entity(iri: str, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        node = await prov_service.soft_delete_node(db, iri)
    if not node:
        raise HTTPException(404, "Entity not found")
    return Response(status_code=204)


# ── Activities ────────────────────────────────────────────────────────────────

@router.post("/activities", status_code=201)
async def create_activity(
    data: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    async with db.begin():
        node = await prov_service.create_activity(db, data)
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings), status_code=201)


@router.get("/activities")
async def list_activities(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    nodes = await prov_service.list_nodes(db, node_type="Activity", limit=limit, offset=offset)
    return JSONLDResponse([node_to_jsonld(n) for n in nodes], _context_url(settings))


@router.get("/activities/{iri:path}")
async def get_activity(
    iri: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    node = await prov_service.get_node_by_iri(db, iri)
    if not node or node.node_type != "Activity":
        raise HTTPException(404, "Activity not found")
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings))


# ── Agents ────────────────────────────────────────────────────────────────────

@router.post("/agents", status_code=201)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    async with db.begin():
        node = await prov_service.create_agent(db, data)
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings), status_code=201)


@router.get("/agents")
async def list_agents(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    nodes = await prov_service.list_nodes(db, node_type="Agent", limit=limit, offset=offset)
    return JSONLDResponse([node_to_jsonld(n) for n in nodes], _context_url(settings))
