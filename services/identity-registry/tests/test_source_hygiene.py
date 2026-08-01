"""Sweeps over this unit's own source that a reviewer would otherwise have to do.

Each one closes a P3 row *and* keeps it closed. They are cheap, and each fails
because of something a change did not do — the same shape as
`test_settings_are_read.py`, which is the only reason that row stays shut.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from identity_registry.schemas.responses import OwnerResponse

UNIT = Path(__file__).resolve().parents[1]
SRC = UNIT / "src" / "identity_registry"
REPO = UNIT.parents[1]


# ── An owner is never reported verified by omission ────────────────


def _owner_fields() -> dict:
    """Every required field except `status`."""
    now = datetime.now(UTC)
    return {
        "id": "acme",
        "type": "organization",
        "name": "Acme",
        "did": None,
        "url": None,
        "aliases": [],
        "organization_config": None,
        "created_at": now,
        "updated_at": now,
    }


def test_owner_response_requires_an_explicit_status():
    """`status` used to default to "verified".

    That is precisely the state migration 0009 removed from the database — a row
    reading as verified while nothing verified it — reintroduced at the API
    boundary, where the consent circle reads it. Both constructors happen to
    pass it, so the default was unreachable and would have stayed invisible
    until a third one was written.
    """
    with pytest.raises(ValidationError) as exc:
        OwnerResponse(**_owner_fields())

    # Named explicitly: `created_at` and `updated_at` are required too, so a
    # bare `pytest.raises` here would pass even if `status` went back to
    # defaulting to "verified".
    missing = {e["loc"][0] for e in exc.value.errors() if e["type"] == "missing"}
    assert missing == {"status"}, f"expected only `status` missing, got {missing}"


def test_owner_response_accepts_a_stated_status():
    """The counterpart, so the test above cannot pass by the model being broken
    in some unrelated way."""
    owner = OwnerResponse(**_owner_fields(), status="pending")
    assert owner.status == "pending"


# ── Cited documentation exists ─────────────────────────────────────


_DOC_REF = re.compile(r"docs/[A-Za-z0-9._/-]+\.md")


def test_every_cited_doc_path_exists():
    """A docstring pointed at `docs/owner-identity-and-ownership.md`, which has
    never existed in this repository.

    A stale pointer is worse than no pointer: a reader burns time looking for
    it, and its absence is invisible to every other check. The path is written
    down, so it can be verified.
    """
    missing: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for ref in sorted(set(_DOC_REF.findall(text))):
            if not (REPO / ref).is_file():
                missing.append(f"{path.relative_to(REPO)} cites {ref}")
    assert missing == [], "citations to files that do not exist:\n  " + "\n  ".join(
        missing
    )


# ── The CLI does not reach for a deprecated loop ───────────────────


def test_the_cli_does_not_use_get_event_loop():
    """`asyncio.get_event_loop()` is deprecated from 3.12 when no loop is
    running and is scheduled to raise; it also returned a loop nothing closed.
    Asserted rather than left to a warning nobody reads in CLI output."""
    body = (SRC / "cli" / "main.py").read_text(encoding="utf-8")
    body = re.sub(r'"""(?:.|\n)*?"""', "", body)  # docstrings name it in prose
    body = re.sub(r"#.*$", "", body, flags=re.MULTILINE)
    assert "get_event_loop" not in body, (
        "ir-cli reaches for asyncio.get_event_loop(); use asyncio.run()"
    )


# ── Generated and fetched material lives at the repo root ──────────


def test_the_unit_has_no_local_data_directory():
    """Root `AGENTS.md`: anything a process writes, downloads or caches goes
    under `./data/<concern>/` at the repo root **and nowhere else**.

    This unit carried a stale local `data/` holding only a `.gitkeep`. It was
    *not* tracked — `.gitignore`'s `data` rule matches this path too, so a fresh
    clone never had it and no commit ever carried it. That is exactly why it
    survived: it is invisible to review, and the only thing that can notice it
    is a check like this one. Nothing referenced it — no Dockerfile, compose
    mount, chart or Taskfile — and the `export_base_path` setting that presumably
    once used it no longer exists on `Settings`.

    The rule exists so the list of scratch locations stays short, and it erodes
    one reasonable-looking exception at a time.
    """
    assert not (UNIT / "data").exists(), (
        "services/identity-registry/data/ is back; generated material belongs "
        "in ./data/<concern>/ at the repo root"
    )
