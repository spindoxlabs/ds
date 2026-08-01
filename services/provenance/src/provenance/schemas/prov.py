"""Pydantic schemas for PROV-O nodes and relations."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel


class NodeBase(BaseModel):
    iri: str
    label: str | None = None
    description: str | None = None
    energy_type: str | None = None
    external_meta: dict[str, Any] | None = None


class EntityCreate(NodeBase):
    pass


class ActivityCreate(NodeBase):
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AgentCreate(NodeBase):
    pass


# No `NodeRead` / `RelationRead`. Every read on this service answers JSON-LD
# built by `services/jsonld_service.py` — an ORM-shaped read model would be a
# second, silently divergent description of the same rows, and both were unused.


#: Every relation type this service will store, whether written through
#: `POST /prov/relations` or by a materialiser.
#:
#: The two vocabularies had drifted apart in both directions: `invalidated` was
#: written by the ingest path (`AccessRevoked`, `ConsentRevoked`) and **rejected**
#: here, so the same edge was legal from one door and a 422 from the other; and
#: `schemas/context.py` defined no term for it, so it expanded to nothing.
#: `tests/test_relation_vocabulary.py` sweeps the materialisers and fails on the
#: next term that appears in one place and not the others.
#:
#: `actedOnBehalfOf` and `wasInformedBy` have no materialiser and stay: this is a
#: general PROV-O graph API, and refusing a valid PROV-O relation because ds does
#: not happen to derive it yet would make the manual door narrower than the
#: vocabulary it publishes.
RelationType = Literal[
    "wasGeneratedBy", "wasAttributedTo", "wasDerivedFrom",
    "wasAssociatedWith", "used", "invalidated",
    "actedOnBehalfOf", "wasInformedBy",
]

#: The same set as a tuple, for the sweep and for anything that has to enumerate
#: it. Derived from the type rather than repeated, so the two cannot disagree.
RELATION_TYPES: tuple[str, ...] = get_args(RelationType)


class RelationCreate(BaseModel):
    relation_type: RelationType
    subject_iri: str
    object_iri: str
    role: str | None = None
    extra: dict[str, Any] | None = None
