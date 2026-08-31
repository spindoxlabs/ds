"""One relation vocabulary, asserted across the three places that hold it.

A relation term lives in three files and nothing tied them together:

- `services/event_service.py` — the materialisers that *write* edges;
- `schemas/prov.py` — `RelationType`, what `POST /prov/relations` will accept;
- `schemas/context.py` — `PROV_CONTEXT`, what the published JSON-LD defines.

They had drifted in both directions at once. `invalidated` was written by two
materialisers, rejected by the schema, and undefined in the context — so the
same edge was legal through one door and a 422 through the other, and expanded
to nothing for any consumer that processed the context (rulebook `L-7`).

This sweeps the materialisers for the terms they actually write and fails on any
that the other two do not carry. A comment cannot fail; this can.
"""

from __future__ import annotations

import pytest

import re
from pathlib import Path

from provenance.schemas.context import PROV_CONTEXT
from provenance.schemas.prov import RELATION_TYPES

_EVENT_SERVICE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "provenance"
    / "services"
    / "event_service.py"
)


def written_relation_types() -> set[str]:
    """Every relation type a materialiser passes to `_edge`."""
    source = _EVENT_SERVICE.read_text()
    return set(re.findall(r'_edge\(\s*session,\s*"([A-Za-z]+)"', source))


@pytest.mark.rule("L-15")
def test_the_sweep_finds_the_materialisers():
    """Guard the guard: a regex that matches nothing would pass every test below."""
    written = written_relation_types()
    assert "wasGeneratedBy" in written
    assert "wasAssociatedWith" in written
    assert len(written) >= 6


@pytest.mark.rule("L-7")
def test_every_written_relation_is_accepted_by_the_relations_route():
    missing = written_relation_types() - set(RELATION_TYPES)
    assert not missing, (
        f"{sorted(missing)} are written by a materialiser but rejected by "
        "POST /prov/relations — the same edge legal through one door and a 422 "
        "through the other"
    )


@pytest.mark.rule("L-7")
def test_every_written_relation_is_defined_in_the_context():
    missing = written_relation_types() - set(PROV_CONTEXT)
    assert not missing, (
        f"{sorted(missing)} are written into the graph but undefined in "
        "PROV_CONTEXT — the edge expands to nothing for any consumer that "
        "processes the context (rulebook L-7)"
    )


@pytest.mark.rule("L-7")
def test_every_accepted_relation_is_defined_in_the_context():
    """The manual door must not admit a term the published graph cannot express."""
    missing = set(RELATION_TYPES) - set(PROV_CONTEXT)
    assert not missing, (
        f"{sorted(missing)} accepted by the API, undefined in PROV_CONTEXT"
    )


@pytest.mark.rule("L-7")
def test_invalidated_is_the_term_that_was_missing():
    """Pins the specific defect, so a future tidy-up that drops it fails here."""
    assert "invalidated" in RELATION_TYPES
    assert PROV_CONTEXT["invalidated"]["@id"] == "prov:invalidated"
    assert "invalidated" in written_relation_types()
