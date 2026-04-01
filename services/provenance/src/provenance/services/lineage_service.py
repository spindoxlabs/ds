"""Async BFS lineage traversal over prov_relations."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ProvNodeORM, ProvRelationORM


@dataclass
class LineageGraph:
    nodes: list[ProvNodeORM]
    edges: list[ProvRelationORM]
    depth_map: dict[str, int]  # iri → depth


async def get_lineage(
    session: AsyncSession,
    root_iri: str,
    direction: str = "both",   # upstream | downstream | both
    max_depth: int = 5,
    relation_types: list[str] | None = None,
) -> LineageGraph:
    result = await session.execute(
        select(ProvNodeORM).where(ProvNodeORM.iri == root_iri)
    )
    root = result.scalar_one_or_none()
    if root is None:
        return LineageGraph(nodes=[], edges=[], depth_map={})

    visited_ids: set[str] = {root.id}
    depth_map: dict[str, int] = {root.iri: 0}
    nodes: list[ProvNodeORM] = [root]
    edges: list[ProvRelationORM] = []
    frontier: set[str] = {root.id}

    for depth in range(1, max_depth + 1):
        if not frontier:
            break

        stmt = select(ProvRelationORM).where(
            ProvRelationORM.subject_id.in_(frontier)
            if direction in ("upstream", "both")
            else ProvRelationORM.subject_id.in_([])
        )
        if direction in ("downstream", "both"):
            stmt = select(ProvRelationORM).where(
                ProvRelationORM.subject_id.in_(frontier)
                | ProvRelationORM.object_id.in_(frontier)
            )
        else:
            stmt = select(ProvRelationORM).where(
                ProvRelationORM.subject_id.in_(frontier)
            )

        if relation_types:
            stmt = stmt.where(ProvRelationORM.relation_type.in_(relation_types))

        rel_result = await session.execute(stmt)
        batch_edges = list(rel_result.scalars().all())

        next_frontier: set[str] = set()
        for edge in batch_edges:
            edges.append(edge)
            for node_id in (edge.subject_id, edge.object_id):
                if node_id not in visited_ids:
                    visited_ids.add(node_id)
                    next_frontier.add(node_id)

        if next_frontier:
            node_result = await session.execute(
                select(ProvNodeORM).where(ProvNodeORM.id.in_(next_frontier))
            )
            new_nodes = list(node_result.scalars().all())
            nodes.extend(new_nodes)
            for node in new_nodes:
                depth_map[node.iri] = depth

        frontier = next_frontier

    return LineageGraph(nodes=nodes, edges=edges, depth_map=depth_map)
