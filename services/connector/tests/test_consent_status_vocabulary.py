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

from connector.db.models import CONSENT_DECIDERS, CONSENT_STATUSES

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

# The same sweep for `decided_by`, whose writers include the routes: the value is
# assigned there as a plain literal (`decided_by="subject"`) and as a conditional
# (`decided_by = "operator" if override else "service"`), so this one reads every
# string on the right-hand side rather than the first.
_DECIDER_ASSIGN = re.compile(r"(?:^|[\s.(])decided_by\s*=\s*(?P<rhs>[^\n]*)")
_STRING = re.compile(r"\"([^\"]*)\"|'([^']*)'")

# Everything that writes the column. The routes are in the list because that is
# where two of the three values are decided — a sweep of the service alone would
# report `operator` as written nowhere and miss a route inventing a fourth.
DECIDER_WRITERS = (
    SRC / "services" / "consent_service.py",
    SRC / "api" / "v1" / "consent.py",
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


def _deciders_written(path: Path) -> set[str]:
    """Every literal assigned to `decided_by` in one module.

    A right-hand side naming no string at all — `decided_by=decided_by`, the
    route passing its own local through — contributes nothing, which is correct:
    the value it carries is written where the local was assigned, and that
    assignment is in this same sweep.
    """
    body = _strip_comments_and_docstrings(path.read_text())
    written: set[str] = set()
    for match in _DECIDER_ASSIGN.finditer(body):
        for a, b in _STRING.findall(match.group("rhs")):
            written.add(a or b)
    return written


@pytest.mark.parametrize("path", DECIDER_WRITERS, ids=lambda p: p.name)
def test_every_written_decider_is_declared(path: Path):
    undeclared = sorted(_deciders_written(path) - set(CONSENT_DECIDERS))
    assert not undeclared, (
        f"{path.name} writes decided_by value(s) {undeclared} that "
        f"CONSENT_DECIDERS does not declare. `D-15c` reads this column to decide "
        f"who may lift a withdrawal, so an undeclared value is an authority "
        f"nobody has ruled on."
    )


def test_the_decider_scan_sees_what_the_routes_write():
    """Guards this scan the way `test_the_scan_sees_the_sweep` guards the other.

    The routes write `subject` (a person's own decision) and `operator` (the
    deployment operator). `service` is **no longer written** since the
    plain-service path was removed (2026-09-17) — it stays declared for the rows
    it wrote, and a route writing it again would be that path coming back.
    """
    written = _deciders_written(SRC / "api" / "v1" / "consent.py")
    assert {"operator", "subject"} <= written
    assert "service" not in written


def test_declared_deciders_are_unique_and_lead_with_the_default():
    assert len(set(CONSENT_DECIDERS)) == len(CONSENT_DECIDERS)
    assert CONSENT_DECIDERS[0] == "subject", (
        "the column's default leads the list, and it is the fail-closed one: an "
        "unclassified withdrawal is treated as the person's own"
    )


def test_the_values_an_organisation_may_state_are_declared_deciders():
    """`decided_by` on the request body is a `Literal`, not an assignment the
    scan above can read; this is the same check for it (plan
    `a-collector-registers-consent-at-the-holder`)."""
    from typing import get_args

    from connector.api.v1.consent import AdminShareRequest

    annotation = AdminShareRequest.model_fields["decided_by"].annotation
    stated = {v for arg in get_args(annotation) for v in get_args(arg)}
    assert stated == {"subject", "collector"}
    assert stated <= set(CONSENT_DECIDERS)


def test_the_database_holds_the_column_to_the_declared_set():
    """Migration 0012 and the model state the same constraint over the same
    values — a value added here and not there would be refused on write."""
    from connector.db.models import ConsentRequestORM

    [check] = [
        c
        for c in ConsentRequestORM.__table__.constraints
        if getattr(c, "name", None) == "ck_consent_decided_by"
    ]
    for decider in CONSENT_DECIDERS:
        assert f"'{decider}'" in str(check.sqltext)
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0012_consent_collector.py"
    ).read_text()
    import ast

    [assigned] = [
        node.value
        for node in ast.parse(migration).body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "DECIDERS" for t in node.targets)
    ]
    assert ast.literal_eval(assigned) == CONSENT_DECIDERS
