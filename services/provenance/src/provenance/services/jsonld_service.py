"""ORM → JSON-LD serialisation."""
from __future__ import annotations

from ..db.models import ProvNodeORM, ProvRelationORM
from .lineage_service import LineageGraph

_TYPE_MAP = {
    "Entity":   "prov:Entity",
    "Activity": "prov:Activity",
    "Agent":    "prov:Agent",
}

# The PROV-O property that names an endpoint of a given kind. `prov:entity`
# means "this end is an Entity" — it is a *type* statement, not a position.
_ENDPOINT_KEY = {
    "Entity":   "prov:entity",
    "Activity": "prov:activity",
    "Agent":    "prov:agent",
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
    """Serialise one edge, naming each end by **what it is**.

    Two facts have to survive and they are not the same fact:

    - *what kind of thing each end is* — published as `prov:entity`,
      `prov:activity` or `prov:agent`, read off the node's own `node_type`. This
      used to be hardcoded subject→`prov:entity`, object→`prov:activity`, so
      `wasAssociatedWith(activity, agent)` published the activity as an entity
      and the agent as an activity. Anything consuming the graph as PROV-O read
      two wrong types per edge (rulebook `L-8`);
    - *which way the edge points* — published as `ds:source` / `ds:target`.
      Typed keys cannot carry this on their own: `wasDerivedFrom` joins two
      Entities and `actedOnBehalfOf` two Agents, so the typed key collides and
      direction would be lost exactly where derivation makes it matter most. On
      a same-type edge the typed key carries both IRIs as a list — still true —
      and `ds:source` / `ds:target` remain the unambiguous reading.

    A consumer splitting nodes from edges should test for `ds:source` /
    `ds:target`, which every edge carries and no node does.
    """
    subject = nodes_by_id.get(edge.subject_id)
    object_ = nodes_by_id.get(edge.object_id)
    obj: dict = {
        "@id": f"urn:relation:{edge.id}",
        "@type": f"prov:{edge.relation_type}",
    }
    if subject:
        obj["ds:source"] = subject.iri
    if object_:
        obj["ds:target"] = object_.iri

    for node in (subject, object_):
        if node is None:
            continue
        key = _ENDPOINT_KEY.get(node.node_type)
        if key is None:
            continue
        if key not in obj:
            obj[key] = node.iri
            continue
        held = obj[key] if isinstance(obj[key], list) else [obj[key]]
        if node.iri not in held:
            held.append(node.iri)
        obj[key] = held

    if edge.role:
        obj["prov:role"] = edge.role
    return obj


def lineage_to_jsonld(graph: LineageGraph) -> list[dict]:
    nodes_by_id = {n.id: n for n in graph.nodes}
    result: list[dict] = [node_to_jsonld(n) for n in graph.nodes]
    result += [relation_to_jsonld(e, nodes_by_id) for e in graph.edges]
    return result
