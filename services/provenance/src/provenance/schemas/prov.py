"""Pydantic schemas for PROV-O nodes and relations."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class NodeRead(NodeBase):
    id: str
    node_type: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    invalidated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RelationCreate(BaseModel):
    relation_type: Literal[
        "wasGeneratedBy", "wasAttributedTo", "wasDerivedFrom",
        "wasAssociatedWith", "used", "actedOnBehalfOf", "wasInformedBy",
    ]
    subject_iri: str
    object_iri: str
    role: str | None = None
    extra: dict[str, Any] | None = None


class RelationRead(BaseModel):
    id: str
    relation_type: str
    subject_iri: str
    object_iri: str
    role: str | None = None
    extra: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
