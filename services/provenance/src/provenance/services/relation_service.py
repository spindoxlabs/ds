"""Insert and query PROV-O edges."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ProvNodeORM, ProvRelationORM
from ..schemas.prov import RelationCreate


async def create_relation(
    session: AsyncSession,
    data: RelationCreate,
) -> tuple[ProvRelationORM, bool]:
    """Insert a relation. Returns (relation, created). created=False means duplicate."""
    subject = await _require_node(session, data.subject_iri)
    object_ = await _require_node(session, data.object_iri)

    relation = ProvRelationORM(
        relation_type=data.relation_type,
        subject_id=subject.id,
        object_id=object_.id,
        role=data.role,
        extra=data.extra,
    )
    session.add(relation)
    try:
        await session.flush()
        return relation, True
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(ProvRelationORM).where(
                ProvRelationORM.relation_type == data.relation_type,
                ProvRelationORM.subject_id == subject.id,
                ProvRelationORM.object_id == object_.id,
            )
        )
        return result.scalar_one(), False


async def get_relations_for_nodes(
    session: AsyncSession,
    node_ids: list[str],
    relation_types: list[str] | None = None,
) -> list[ProvRelationORM]:
    stmt = select(ProvRelationORM).where(
        ProvRelationORM.subject_id.in_(node_ids)
        | ProvRelationORM.object_id.in_(node_ids)
    )
    if relation_types:
        stmt = stmt.where(ProvRelationORM.relation_type.in_(relation_types))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _require_node(session: AsyncSession, iri: str) -> ProvNodeORM:
    result = await session.execute(select(ProvNodeORM).where(ProvNodeORM.iri == iri))
    node = result.scalar_one_or_none()
    if node is None:
        raise ValueError(f"Node not found: {iri}")
    return node
