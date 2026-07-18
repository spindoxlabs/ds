"""Participant registry — reads providers from identity-registry API or YAML."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

log = logging.getLogger(__name__)


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


def load_providers_from_registry(
    identity_registry_url: str,
    headers: dict[str, str] | None = None,
) -> list[Provider]:
    """Fetch providers from the identity-registry /admin/participants API."""
    url = f"{identity_registry_url.rstrip('/')}/admin/participants"
    try:
        resp = httpx.get(url, timeout=10.0, headers=headers or {})
        resp.raise_for_status()
        return [
            Provider(id=p["did"], dsp_address=p.get("dsp_address") or "")
            for p in resp.json()
            if p.get("role") == "provider" and p.get("dsp_address")
        ]
    except httpx.HTTPError as exc:
        log.error("Failed to fetch providers from identity-registry: %s", exc)
        return []


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
