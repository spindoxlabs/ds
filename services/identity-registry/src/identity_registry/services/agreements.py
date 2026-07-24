"""Service-agreement loading + import (Block D §5.4).

YAML-seeded, IR-hosted, following the ``owner import`` / ``membership import``
pattern. The agreement text lives in per-locale markdown files; we store only
their path and SHA-256 — codes and hashes, never inline prose (§2.4).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Agreement
from ..schemas.requests import VALID_CAPACITIES


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_effective_from(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_agreements_file(path: Path) -> list[dict]:
    """Parse an agreements YAML file into normalised entries.

    Text file paths in ``text: {locale: relative/path.md}`` are resolved
    relative to the YAML file and read to compute a per-locale SHA-256. Raises
    ``FileNotFoundError`` for a missing text file and ``ValueError`` for an
    invalid ``capacity``.
    """
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    entries: list[dict] = []
    for raw in data.get("agreements", []):
        capacity = raw["capacity"]
        if capacity not in VALID_CAPACITIES:
            raise ValueError(
                f"Agreement {raw.get('id')!r}: invalid capacity {capacity!r}. "
                f"Must be one of {sorted(VALID_CAPACITIES)}"
            )

        texts: dict[str, dict] = {}
        for locale, rel_path in (raw.get("text") or {}).items():
            text_path = (path.parent / rel_path).resolve()
            if not text_path.exists():
                raise FileNotFoundError(
                    f"Agreement {raw.get('id')!r} locale {locale!r}: "
                    f"text file not found: {text_path}"
                )
            content = text_path.read_text(encoding="utf-8")
            texts[locale] = {"path": rel_path, "sha256": _sha256_text(content)}

        entries.append(
            {
                "id": raw["id"],
                "version": str(raw["version"]),
                "effective_from": _parse_effective_from(raw.get("effective_from")),
                "applies_to": raw.get("applies_to", []),
                "capacity": capacity,
                "texts": texts,
            }
        )
    return entries


async def import_agreements(db: AsyncSession, entries: list[dict]) -> int:
    """Idempotent upsert of agreement definitions keyed by (id, version)."""
    count = 0
    for entry in entries:
        result = await db.execute(
            select(Agreement).where(
                Agreement.id == entry["id"],
                Agreement.version == entry["version"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.effective_from = entry["effective_from"]
            existing.applies_to = entry["applies_to"]
            existing.capacity = entry["capacity"]
            existing.texts = entry["texts"]
            existing.updated_at = datetime.now(UTC)
        else:
            db.add(Agreement(**entry))
        count += 1
    await db.flush()
    return count
