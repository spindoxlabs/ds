"""Sweeps over this unit's own source that a reviewer would otherwise have to do.

Each one closes a P3 row *and* keeps it closed. They are cheap, and each fails
because of something a change did not do — the same shape as
`test_settings_are_read.py`, which is the only reason that row stays shut.
Ported from `services/identity-registry`.
"""

from __future__ import annotations

import re
from pathlib import Path

from provenance.db.models import DomainEventORM

UNIT = Path(__file__).resolve().parents[1]
SRC = UNIT / "src" / "provenance"
REPO = UNIT.parents[1]


# ── Cited documentation exists ─────────────────────────────────────

_DOC_REF = re.compile(r"docs/[A-Za-z0-9._/-]+\.md")


def test_every_cited_doc_path_exists():
    """A stale pointer is worse than no pointer: a reader burns time looking for
    it, and its absence is invisible to every other check."""
    missing: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for ref in sorted(set(_DOC_REF.findall(text))):
            if not (REPO / ref).is_file():
                missing.append(f"{path.relative_to(REPO)} cites {ref}")
    assert missing == [], "citations to files that do not exist:\n  " + "\n  ".join(
        missing
    )


# ── One chart per service, at the repo root ────────────────────────


def test_the_unit_has_no_local_chart():
    """`helm/charts/ds-provenance` is the chart. The unit-local `charts/` was an
    orphan: nothing referenced it — no Taskfile, no helmfile — and it set none of
    the OIDC, service-client or trust-anchor variables the real chart does, so a
    `DS_ENV=production` deploy from it failed all four `ProductionGuard` checks.
    Two charts for one service means the wrong one gets edited."""
    assert not (UNIT / "charts").exists(), (
        "services/provenance/charts/ is back; the chart is helm/charts/ds-provenance"
    )


# ── Generated and fetched material lives at the repo root ──────────


def test_the_unit_has_no_local_data_or_config_directory():
    """ADR-0008: anything a process writes, downloads or caches goes under
    `./data/<concern>/` at the repo root **and nowhere else**.

    This unit carried both a `data/` (untracked, `.gitignore`'s `data` rule
    matches it, so invisible to review) and a `config/` holding nothing but a
    `.gitkeep`. Neither was referenced by a Dockerfile, a compose mount, a chart
    or a Taskfile — which is exactly why they survived. The rule exists so the
    list of scratch locations stays short, and it erodes one reasonable-looking
    exception at a time.
    """
    for name in ("data", "config"):
        assert not (UNIT / name).exists(), (
            f"services/provenance/{name}/ is back; generated material belongs in "
            "./data/<concern>/ at the repo root"
        )


# ── The event log has no state it does not track ───────────────────


def test_domain_events_has_no_processed_flag():
    """It was written `True` unconditionally and read by nothing — a column
    describing an asynchronous queue this service does not have. `NOT NULL` with
    a `False` default means the next writer that forgets it records every event
    as unprocessed, which reads as a backlog. Dropped in migration `0003`."""
    assert "processed" not in DomainEventORM.__table__.columns


def test_the_subject_composite_index_is_declared_on_the_model():
    """It existed only in migration `0002`, so `alembic revision --autogenerate`
    proposed dropping it: the index serving the one query it was built for would
    have been removed by the next unrelated schema change, silently."""
    names = {index.name for index in DomainEventORM.__table__.indexes}
    assert "ix_domain_events_subject_occurred" in names
