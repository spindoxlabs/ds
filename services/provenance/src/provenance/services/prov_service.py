"""CRUD operations for PROV-O nodes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ProvNodeORM
from ..schemas.prov import EntityCreate, ActivityCreate, AgentCreate

log = logging.getLogger(__name__)


def _merged_meta(existing: dict | None, incoming: dict) -> dict:
    """Later facts about a node add to what is known, they do not replace it.

    Two events routinely describe the same node from different sides:
    ``NegotiationStarted`` records the ``offerId`` and ``NegotiationFinalized``
    the ``agreementId``, both on ``urn:activity:negotiation:<id>``. Replacing the
    block dropped the first fact the moment the second arrived, so a finalized
    negotiation could no longer say which offer it came from.

    ``None`` on the incoming side means *this event does not know*, never *forget
    what you knew* — so it is dropped rather than written over a real value.
    """
    merged = dict(existing or {})
    merged.update({k: v for k, v in incoming.items() if v is not None})
    return merged


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
        return node

    # A node's PROV-O type belongs to the node, not to the position it happened
    # to occupy in the first event that mentioned it (rulebook `L-8`). Matching
    # on IRI alone and never revisiting `node_type` froze that first guess
    # permanently — and the graph then published the wrong `@type` for the node
    # and, through it, the wrong endpoint key for every edge touching it.
    if node.node_type != node_type:
        log.info("prov node %s reclassified %s → %s", iri, node.node_type, node_type)
        node.node_type = node_type

    for k, v in fields.items():
        if v is None:
            continue
        if k == "external_meta":
            node.external_meta = _merged_meta(node.external_meta, v)
        else:
            setattr(node, k, v)
    return node


async def get_node_by_iri(session: AsyncSession, iri: str) -> ProvNodeORM | None:
    result = await session.execute(select(ProvNodeORM).where(ProvNodeORM.iri == iri))
    return result.scalar_one_or_none()


async def create_entity(session: AsyncSession, data: EntityCreate) -> ProvNodeORM:
    return await upsert_node(
        session,
        data.iri,
        "Entity",
        label=data.label,
        description=data.description,
        energy_type=data.energy_type,
        external_meta=data.external_meta,
    )


async def create_activity(session: AsyncSession, data: ActivityCreate) -> ProvNodeORM:
    return await upsert_node(
        session,
        data.iri,
        "Activity",
        label=data.label,
        description=data.description,
        energy_type=data.energy_type,
        external_meta=data.external_meta,
        started_at=data.started_at,
        ended_at=data.ended_at,
    )


async def create_agent(session: AsyncSession, data: AgentCreate) -> ProvNodeORM:
    return await upsert_node(
        session,
        data.iri,
        "Agent",
        label=data.label,
        description=data.description,
        energy_type=data.energy_type,
        external_meta=data.external_meta,
    )


async def soft_delete_node(
    session: AsyncSession, iri: str, node_type: str | None = None
) -> ProvNodeORM | None:
    """Invalidate a node, optionally only if it is of the expected type.

    The type check matters now that all three collections have a `DELETE`: without
    it `DELETE /prov/agents/<iri>` would happily invalidate an Entity, so a caller
    could remove a node from a collection it was never allowed to enumerate.
    """
    node = await get_node_by_iri(session, iri)
    if node is None or (node_type is not None and node.node_type != node_type):
        return None
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
