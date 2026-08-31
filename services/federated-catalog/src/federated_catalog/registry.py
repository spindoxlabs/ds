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


def _is_provider(participant: dict[str, Any]) -> bool:
    """Whether a registry participant offers data.

    The identity-registry models this as ``roles`` — a *list*, because a
    participant can be both provider and consumer. Reading the singular
    ``role`` (which the API never returns) matched nothing, so every crawl
    found zero providers and the catalogue was silently empty rather than
    wrong. The singular key is still tolerated for any older payload.
    """
    roles = participant.get("roles")
    if isinstance(roles, (list, tuple, set)):
        return "provider" in roles
    return participant.get("role") == "provider" or roles == "provider"


def _is_active(participant: dict[str, Any]) -> bool:
    """Whether a registry participant is still admitted to the dataspace.

    Deactivated participants must not be crawled (rulebook `C-3`). A missing
    ``active`` key is read as **not** active: the field is part of the response
    model, so its absence means this is not a payload we understand, and an
    index that guesses "probably still admitted" republishes the offerings of a
    participant that was removed.
    """
    return participant.get("active") is True


def load_providers_from_registry(
    identity_registry_url: str,
    headers: dict[str, str] | None = None,
) -> list[Provider]:
    """Fetch active providers from the identity-registry /admin/participants API.

    ``active_only`` and the ``active`` filter below are deliberately both here.
    The route already narrows to active participants for any caller without
    ``identity-registry.admin``, and this service holds only
    ``identity-registry.read`` — so today the filter is defence in depth. It is
    one grant away from being the only thing standing between a deactivated
    participant and the federated catalogue, and the crawl is the side that
    knows it must not publish one (rulebook `C-3`).
    """
    url = f"{identity_registry_url.rstrip('/')}/admin/participants"
    try:
        resp = httpx.get(
            url, timeout=10.0, headers=headers or {}, params={"active_only": "true"}
        )
        resp.raise_for_status()
        providers = []
        for p in resp.json():
            if not (_is_provider(p) and p.get("dsp_address")):
                continue
            if not _is_active(p):
                log.info("Skipping deactivated participant %s", p.get("did"))
                continue
            providers.append(
                Provider(id=p["did"], dsp_address=p.get("dsp_address") or "")
            )
        return providers
    except httpx.HTTPError as exc:
        log.error("Failed to fetch providers from identity-registry: %s", exc)
        return []


def load_providers(yaml_path: str) -> list[Provider]:
    """Return all participants with role=provider from the YAML file.

    The empty-string guard is not cosmetic. ``participants_yaml`` defaults to
    ``""`` — it is the fallback used only when no registry URL is configured —
    and ``Path("")`` is ``Path(".")``, which *exists*. So "no file configured"
    reached ``open()`` on the working directory and raised ``IsADirectoryError``
    instead of returning nothing, which is what ``fc-cli status`` did with no
    arguments. ``load_dcat_sources`` has had this guard all along.
    """
    if not yaml_path:
        return []
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
