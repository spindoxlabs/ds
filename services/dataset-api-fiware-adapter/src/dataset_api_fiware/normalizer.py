from __future__ import annotations

from typing import Any


def normalize_single_entity(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a single-entity QL response into flat rows.

    QL shape:
        {"entityId": "x", "index": [t1, t2],
         "attributes": [{"attrName": "a", "values": [v1, v2]}]}
    Output:
        [{"entity_id": "x", "timestamp": t1, "a": v1},
         {"entity_id": "x", "timestamp": t2, "a": v2}]
    """
    entity_id = data.get("entityId", "")
    index = data.get("index", [])
    attributes = data.get("attributes", [])

    if not index:
        return []

    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(index):
        row: dict[str, Any] = {"entity_id": entity_id, "timestamp": ts}
        for attr in attributes:
            attr_name = attr.get("attrName", "")
            values = attr.get("values", [])
            row[attr_name] = values[i] if i < len(values) else None
        rows.append(row)
    return rows


def normalize_multi_entity(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a multi-entity (by-type) QL response into flat rows.

    QL shape:
        {"entityType": "T",
         "entities": [
             {"entityId": "x", "index": [...], "values": [...]},
             ...
         ],
         "attrName": "a"}
    """
    attr_name = data.get("attrName", "")
    entities = data.get("entities", [])

    rows: list[dict[str, Any]] = []
    for ent in entities:
        entity_id = ent.get("entityId", "")
        index = ent.get("index", [])
        values = ent.get("values", [])
        for i, ts in enumerate(index):
            rows.append({
                "entity_id": entity_id,
                "timestamp": ts,
                attr_name: values[i] if i < len(values) else None,
            })
    return rows


def normalize_entities_list(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a list-entities response (last-value style).

    QL shape: [{"id": "x", "type": "T", "attr1": {"value": v, ...}, ...}, ...]
    """
    rows: list[dict[str, Any]] = []
    for ent in data:
        row: dict[str, Any] = {
            "entity_id": ent.get("id", ""),
            "entity_type": ent.get("type", ""),
        }
        for key, val in ent.items():
            if key in ("id", "type"):
                continue
            if isinstance(val, dict) and "value" in val:
                row[key] = val["value"]
            else:
                row[key] = val
        rows.append(row)
    return rows


def normalize_response(
    data: Any,
    *,
    is_single_entity: bool = False,
    is_multi_entity: bool = False,
    is_entities_list: bool = False,
) -> list[dict[str, Any]]:
    """Dispatch to the right normalizer based on query shape."""
    if is_entities_list:
        if isinstance(data, list):
            return normalize_entities_list(data)
        return []

    if not isinstance(data, dict):
        return []

    if is_single_entity:
        return normalize_single_entity(data)

    if is_multi_entity:
        return normalize_multi_entity(data)

    # Auto-detect from response shape
    if "entityId" in data:
        return normalize_single_entity(data)
    if "entities" in data:
        return normalize_multi_entity(data)

    return []
