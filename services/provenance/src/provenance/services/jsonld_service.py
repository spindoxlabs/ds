"""ORM → JSON-LD serialisation."""
from __future__ import annotations

from ..db.models import ProvNodeORM, ProvRelationORM, AccessLogORM
from .lineage_service import LineageGraph

_TYPE_MAP = {
    "Entity":   "prov:Entity",
    "Activity": "prov:Activity",
    "Agent":    "prov:Agent",
}


def node_to_jsonld(node: ProvNodeORM) -> dict:
    obj: dict = {
        "@id": node.iri,
        "@type": _TYPE_MAP.get(node.node_type, node.node_type),
        "prov:label": node.label,
        "prov:description": node.description,
    }
    if node.energy_type:
        obj["@type"] = [obj["@type"], node.energy_type]
    if node.started_at:
        obj["prov:startedAtTime"] = node.started_at.isoformat()
    if node.ended_at:
        obj["prov:endedAtTime"] = node.ended_at.isoformat()
    if node.external_meta:
        obj.update(node.external_meta)
    # strip None values
    return {k: v for k, v in obj.items() if v is not None}


def relation_to_jsonld(edge: ProvRelationORM, nodes_by_id: dict[str, ProvNodeORM]) -> dict:
    subject = nodes_by_id.get(edge.subject_id)
    object_ = nodes_by_id.get(edge.object_id)
    obj: dict = {
        "@id": f"urn:relation:{edge.id}",
        "@type": f"prov:{edge.relation_type}",
    }
    if subject:
        obj["prov:entity"] = subject.iri
    if object_:
        obj["prov:activity"] = object_.iri
    if edge.role:
        obj["prov:role"] = edge.role
    return obj


def lineage_to_jsonld(graph: LineageGraph) -> list[dict]:
    nodes_by_id = {n.id: n for n in graph.nodes}
    result: list[dict] = [node_to_jsonld(n) for n in graph.nodes]
    result += [relation_to_jsonld(e, nodes_by_id) for e in graph.edges]
    return result
