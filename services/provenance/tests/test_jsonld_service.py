"""The lineage JSON-LD contract the portal reads.

`relation_to_jsonld` publishes two independent facts per edge and both have a
consumer:

- **direction**, as `ds:source` / `ds:target`. `services/portal`'s
  `classifyLineageGraph` splits the graph on these — every edge has them, no node
  does. It once split on `subject` / `object` (which nothing emitted, so zero
  edges rendered) and then on `prov:entity` + `prov:activity` (which only
  `wasGeneratedBy` and `used` both carry, so most edges still vanished);
- **what each end is**, as `prov:entity` / `prov:activity` / `prov:agent`, taken
  from the node's own `node_type`. These were hardcoded by position, so every
  edge published two wrong PROV-O types.

This pins both so the two ends cannot drift apart again.
"""

from __future__ import annotations

import pytest

from types import SimpleNamespace

from provenance.services.jsonld_service import relation_to_jsonld


def _node(id_: str, iri: str, node_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=id_, iri=iri, node_type=node_type)


def _edge(
    relation_type: str, subject_id: str, object_id: str, role=None
) -> SimpleNamespace:
    return SimpleNamespace(
        id="r1",
        relation_type=relation_type,
        subject_id=subject_id,
        object_id=object_id,
        role=role,
    )


def test_direction_is_published_on_every_edge():
    dataset = _node("n1", "urn:dataset:meters", "Entity")
    activity = _node("n2", "urn:activity:ingest", "Activity")

    out = relation_to_jsonld(
        _edge("wasGeneratedBy", "n1", "n2"), {"n1": dataset, "n2": activity}
    )

    assert out["@type"] == "prov:wasGeneratedBy"
    assert out["ds:source"] == "urn:dataset:meters"
    assert out["ds:target"] == "urn:activity:ingest"
    # The keys an earlier version wrongly published direction under.
    assert "subject" not in out
    assert "object" not in out


@pytest.mark.rule("L-8")
def test_endpoints_are_keyed_by_the_nodes_own_type():
    dataset = _node("n1", "urn:dataset:meters", "Entity")
    activity = _node("n2", "urn:activity:ingest", "Activity")

    out = relation_to_jsonld(
        _edge("wasGeneratedBy", "n1", "n2"), {"n1": dataset, "n2": activity}
    )

    assert out["prov:entity"] == "urn:dataset:meters"
    assert out["prov:activity"] == "urn:activity:ingest"


@pytest.mark.rule("L-8")
def test_an_agent_endpoint_is_an_agent_not_an_activity():
    """The whole defect, in one edge.

    `wasAssociatedWith(activity, agent)` used to publish the activity as
    `prov:entity` and the agent as `prov:activity` — two false type statements
    on the commonest edge in the graph.
    """
    activity = _node("n1", "urn:activity:ingest", "Activity")
    agent = _node("n2", "did:web:provider.test", "Agent")

    out = relation_to_jsonld(
        _edge("wasAssociatedWith", "n1", "n2"), {"n1": activity, "n2": agent}
    )

    assert out["prov:activity"] == "urn:activity:ingest"
    assert out["prov:agent"] == "did:web:provider.test"
    assert "prov:entity" not in out


@pytest.mark.rule("L-8")
def test_a_same_type_edge_keeps_both_ends_and_stays_directional():
    """`wasDerivedFrom` joins two Entities, so the typed key cannot carry both
    ends separately. It carries both as a list — still true — and direction is
    read off `ds:source` / `ds:target`, which is why they exist."""
    copy = _node("n1", "urn:entity:copy", "Entity")
    source = _node("n2", "urn:entity:source", "Entity")

    out = relation_to_jsonld(
        _edge("wasDerivedFrom", "n1", "n2"), {"n1": copy, "n2": source}
    )

    assert out["prov:entity"] == ["urn:entity:copy", "urn:entity:source"]
    assert out["ds:source"] == "urn:entity:copy"
    assert out["ds:target"] == "urn:entity:source"


def test_role_survives():
    activity = _node("n1", "urn:activity:revoke", "Activity")
    agent = _node("n2", "did:example:subject", "Agent")

    out = relation_to_jsonld(
        _edge("wasAssociatedWith", "n1", "n2", role="dataSubject"),
        {"n1": activity, "n2": agent},
    )

    assert out["prov:role"] == "dataSubject"
