"""CRUD operations for PROV-O nodes."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ProvNodeORM
from ..schemas.prov import EntityCreate, ActivityCreate, AgentCreate


async def upsert_node(
    session: AsyncSession,
    iri: str,
    node_type: str,
    **fields,
) -> ProvNodeORM:
    result = await session.execute(select(ProvNodeORM).where(ProvNodeORM.iri == iri))
    node = result.scalar_one_or_none()
    if node is None:
        node = ProvNodeORM(iri=iri, node_type=node_type, **fields)
        session.add(node)
    else:
        for k, v in fields.items():
            if v is not None:
                setattr(node, k, v)
    return node


async def get_node_by_iri(session: AsyncSession, iri: str) -> ProvNodeORM | None:
    result = await session.execute(select(ProvNodeORM).where(ProvNodeORM.iri == iri))
    return result.scalar_one_or_none()


async def create_entity(session: AsyncSession, data: EntityCreate) -> ProvNodeORM:
    return await upsert_node(session, data.iri, "Entity",
                             label=data.label, description=data.description,
                             energy_type=data.energy_type, external_meta=data.external_meta)


async def create_activity(session: AsyncSession, data: ActivityCreate) -> ProvNodeORM:
    return await upsert_node(session, data.iri, "Activity",
                             label=data.label, description=data.description,
                             energy_type=data.energy_type, external_meta=data.external_meta,
                             started_at=data.started_at, ended_at=data.ended_at)


async def create_agent(session: AsyncSession, data: AgentCreate) -> ProvNodeORM:
    return await upsert_node(session, data.iri, "Agent",
                             label=data.label, description=data.description,
                             energy_type=data.energy_type, external_meta=data.external_meta)


async def soft_delete_node(session: AsyncSession, iri: str) -> ProvNodeORM | None:
    node = await get_node_by_iri(session, iri)
    if node:
        node.invalidated_at = datetime.now(timezone.utc)
    return node


async def list_nodes(
    session: AsyncSession,
    node_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ProvNodeORM]:
    stmt = select(ProvNodeORM).where(ProvNodeORM.invalidated_at.is_(None))
    if node_type:
        stmt = stmt.where(ProvNodeORM.node_type == node_type)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())
