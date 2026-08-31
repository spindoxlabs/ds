"""Every consent status the code writes is a status the model declares.

The kind of test this is matters. Like `test_settings_are_read.py`, it can fail
because of something a change *did not* do — declare a new status — rather than
because of something it did. A comment cannot fail; this can.

What it caught: the model listed `pending | granted | rejected | revoked` while
`services/pending_sweep.py` also writes `expired` and `GET /consent/pending`
projects it. A reader of the model therefore concluded a consent row leaves
`pending` only when somebody decides it, and the TTL sweep — the one path that
moves a row with nobody deciding anything — was invisible from the schema.

The scan is source-level on purpose. Asserting against the statuses a test run
happens to produce would only ever prove the paths that test exercises, and the
sweep is exactly the path a unit suite is least likely to reach.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from connector.db.models import CONSENT_STATUSES

SRC = Path(__file__).resolve().parents[1] / "src" / "connector"

# Modules that assign a consent row's status. Listed rather than globbed so that
# a new writer in a new module is a deliberate addition here, not a silent one.
WRITERS = (
    SRC / "services" / "consent_service.py",
    SRC / "services" / "pending_sweep.py",
)

# `status="granted"`, `row.status = EXPIRED`, `consent.status = "revoked"`.
_ASSIGN = re.compile(
    r"(?:^|[\s.(])status\s*=\s*(?P<value>\"[^\"]*\"|'[^']*'|[A-Z_][A-Z0-9_]*)"
)


def _strip_comments_and_docstrings(text: str) -> str:
    """A status named in prose is not a status the code writes.

    Same trap `test_settings_are_read.py` records: without this, the very comment
    this test exists to keep honest would satisfy it.
    """
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    text = re.sub(r"'''(?:.|\n)*?'''", "", text)
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _module_constants(text: str) -> dict[str, str]:
    """`EXPIRED = "expired"` — a writer may assign through a constant."""
    return {
        m.group("name"): m.group("value").strip("\"'")
        for m in re.finditer(
            r"^(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>\"[^\"]*\"|'[^']*')$",
            text,
            re.MULTILINE,
        )
    }


def _statuses_written(path: Path) -> set[str]:
    raw = path.read_text()
    constants = _module_constants(raw)
    body = _strip_comments_and_docstrings(raw)

    written: set[str] = set()
    for match in _ASSIGN.finditer(body):
        value = match.group("value")
        if value.startswith(('"', "'")):
            written.add(value.strip("\"'"))
        elif value in constants:
            written.add(constants[value])
    return written


@pytest.mark.parametrize("path", WRITERS, ids=lambda p: p.name)
def test_every_written_status_is_declared(path: Path):
    undeclared = sorted(_statuses_written(path) - set(CONSENT_STATUSES))
    assert not undeclared, (
        f"{path.name} writes consent status(es) {undeclared} that "
        f"CONSENT_STATUSES does not declare. Add them there — the model's "
        f"vocabulary is what a reader of the schema goes by."
    )


def test_the_scan_sees_the_sweep():
    """Guards the scan itself.

    The failure mode of a source-scanning test is silence: a regex that matches
    nothing passes every assertion above it. `expired` is written through a
    module constant and by no other path, so finding it proves both that the
    scan reads the sweep and that it follows a constant to its value.
    """
    assert "expired" in _statuses_written(SRC / "services" / "pending_sweep.py")


def test_declared_statuses_are_unique_and_ordered_by_lifecycle():
    assert len(set(CONSENT_STATUSES)) == len(CONSENT_STATUSES)
    assert CONSENT_STATUSES[0] == "pending", "the column's default leads the list"
