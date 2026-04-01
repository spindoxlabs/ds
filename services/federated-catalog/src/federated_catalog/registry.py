"""Participant registry — reads providers from participants.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Provider:
    id: str
    dsp_address: str


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
