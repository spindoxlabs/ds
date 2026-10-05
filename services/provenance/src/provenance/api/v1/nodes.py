"""Entities, Activities, Agents: create and read.

**Append-only** (`L-17`). There is no update and no delete: a `POST` naming an IRI
that already exists answers 409 with the node as recorded, exactly as
`POST /prov/relations` does for an edge. The `DELETE` routes soft-deleted a node
for any holder of `provenance.write`, which made the record erasable by the
same principal that writes it. A node changes only through an ingested event,
and every event is in the hash chain.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...dependencies import (
    get_db,
    get_settings_dep,
    require_read_scope,
    require_write_scope,
)
from ...schemas.context import JSONLDResponse
from ...schemas.prov import ActivityCreate, AgentCreate, EntityCreate
from ...services import prov_service
from ...services.jsonld_service import node_to_jsonld

router = APIRouter()

#: The same ceiling `GET /prov/events` has carried all along. Unbounded, these
#: three listings let one request ask for the whole graph — a `limit=0` returned
#: nothing at all and a negative `offset` was a database error, both silently.
MAX_LIMIT = 500

Limit = Query(default=50, ge=1, le=MAX_LIMIT)
Offset = Query(default=0, ge=0)


def _context_url(settings: Settings) -> str:
    return settings.context_url


#: Advertised on every create route: re-posting is the commonest non-error outcome.
CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"description": "The IRI already exists; the node as recorded is returned"},
}


async def _create(db: AsyncSession, settings: Settings, iri: str, create, data):
    async with db.begin():
        existing = await prov_service.get_node_by_iri(db, iri)
        if existing is None:
            node = await create(db, data)
    if existing is not None:
        return JSONLDResponse(
            [node_to_jsonld(existing)], _context_url(settings), status_code=409
        )
    return JSONLDResponse(
        [node_to_jsonld(node)], _context_url(settings), status_code=201
    )


# ── Entities ──────────────────────────────────────────────────────────────────


@router.post(
    "/entities",
    status_code=201,
    responses=CREATE_RESPONSES,
    dependencies=[Depends(require_write_scope)],
)
async def create_entity(
    data: EntityCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    return await _create(db, settings, data.iri, prov_service.create_entity, data)


@router.get("/entities", dependencies=[Depends(require_read_scope)])
async def list_entities(
    limit: int = Limit,
    offset: int = Offset,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    nodes = await prov_service.list_nodes(
        db, node_type="Entity", limit=limit, offset=offset
    )
    return JSONLDResponse([node_to_jsonld(n) for n in nodes], _context_url(settings))


@router.get("/entities/{iri:path}", dependencies=[Depends(require_read_scope)])
async def get_entity(
    iri: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    node = await prov_service.get_node_by_iri(db, iri)
    if not node or node.node_type != "Entity":
        raise HTTPException(404, "Entity not found")
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings))



# ── Activities ────────────────────────────────────────────────────────────────


@router.post(
    "/activities",
    status_code=201,
    responses=CREATE_RESPONSES,
    dependencies=[Depends(require_write_scope)],
)
async def create_activity(
    data: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    return await _create(db, settings, data.iri, prov_service.create_activity, data)


@router.get("/activities", dependencies=[Depends(require_read_scope)])
async def list_activities(
    limit: int = Limit,
    offset: int = Offset,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    nodes = await prov_service.list_nodes(
        db, node_type="Activity", limit=limit, offset=offset
    )
    return JSONLDResponse([node_to_jsonld(n) for n in nodes], _context_url(settings))


@router.get("/activities/{iri:path}", dependencies=[Depends(require_read_scope)])
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


@router.post(
    "/agents",
    status_code=201,
    responses=CREATE_RESPONSES,
    dependencies=[Depends(require_write_scope)],
)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    return await _create(db, settings, data.iri, prov_service.create_agent, data)


@router.get("/agents", dependencies=[Depends(require_read_scope)])
async def list_agents(
    limit: int = Limit,
    offset: int = Offset,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    nodes = await prov_service.list_nodes(
        db, node_type="Agent", limit=limit, offset=offset
    )
    return JSONLDResponse([node_to_jsonld(n) for n in nodes], _context_url(settings))


# Declared after the literal `/agents`, which is the only ordering that keeps the
# listing reachable: a `{iri:path}` route mounted first swallows it.
@router.get("/agents/{iri:path}", dependencies=[Depends(require_read_scope)])
async def get_agent(
    iri: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    node = await prov_service.get_node_by_iri(db, iri)
    if not node or node.node_type != "Agent":
        raise HTTPException(404, "Agent not found")
    return JSONLDResponse([node_to_jsonld(node)], _context_url(settings))

