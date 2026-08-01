"""The lineage JSON-LD contract the portal reads.

`relation_to_jsonld` must emit each edge's endpoints under `prov:entity` /
`prov:activity` — the keys `services/portal`'s `classifyLineageGraph` splits the
graph on. It once read `subject` / `object`, which nothing emits, so the graph
view rendered every node and zero edges. This pins the shape so the two ends
cannot drift apart again.
"""
from __future__ import annotations

from types import SimpleNamespace

from provenance.services.jsonld_service import relation_to_jsonld


def test_relation_emits_prov_entity_and_activity_keys():
    subject = SimpleNamespace(id="n1", iri="urn:dataset:meters")
    object_ = SimpleNamespace(id="n2", iri="urn:activity:ingest")
    edge = SimpleNamespace(
        id="r1", relation_type="wasGeneratedBy", subject_id="n1", object_id="n2", role=None
    )

    out = relation_to_jsonld(edge, {"n1": subject, "n2": object_})

    assert out["@type"] == "prov:wasGeneratedBy"
    assert out["prov:entity"] == "urn:dataset:meters"
    assert out["prov:activity"] == "urn:activity:ingest"
    # The portal reads the two keys above; the keys it used to (wrongly) read
    # must not reappear, or the classifier silently drops every edge again.
    assert "subject" not in out
    assert "object" not in out
