"""Participant registry — reads providers and DCAT sources from YAML."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Provider:
    id: str
    dsp_address: str


@dataclass
class DcatSource:
    id: str
    url: str
    type: str = "dcat-ap"
    defaults: dict[str, Any] = field(default_factory=dict)


def load_providers(yaml_path: str) -> list[Provider]:
    """Return all participants with role=provider from the YAML file."""
    path = Path(yaml_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return [
        Provider(id=p["id"], dsp_address=p["dsp_address"])
        for p in (raw.get("participants") or [])
        if p.get("role") == "provider"
    ]


def load_dcat_sources(yaml_path: str) -> list[DcatSource]:
    """Return DCAT-AP sources from a catalogues.yaml file."""
    if not yaml_path:
        return []
    path = Path(yaml_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return [
        DcatSource(
            id=c["id"],
            url=c["url"],
            type=c.get("type", "dcat-ap"),
            defaults=c.get("defaults") or {},
        )
        for c in (raw.get("catalogues") or [])
        if "id" in c and "url" in c
    ]
