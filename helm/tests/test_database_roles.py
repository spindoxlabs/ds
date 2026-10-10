"""Each release logs in to its database as that database's owner role.

The charts provision nothing in Postgres: the operator creates one database and one
owner role of the same name per service (docs/deployment/operations.md, "Adding a
participant"), and each release's Secret carries `DB_USER`, which Kubernetes
interpolates into the URL. A `DB_USER` naming another release's role authenticates
against the wrong password and the migration init container fails with
`password authentication failed` — which the first cluster install (the deployment's
rehearsal, 2026-10-09) hit on every participant registry: they logged in as the
anchor's `identity_registry`.

*Red:* default a chart's `DB_USER` to anything but the database its URL names.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from conftest import PilotRender, _render, container_env, release_of

URL = re.compile(r"\$\(DB_USER\):\$\(DB_PASSWORD\)@[^/]+/([^?]+)\?")


def _pairs(objects: list[dict]) -> list[tuple[str, str, str]]:
    """(release, database in the URL, DB_USER in the release's Secret)."""
    secrets = {
        (release_of(o), o["metadata"]["name"]): (o.get("stringData") or {})
        for o in objects
        if o["kind"] == "Secret"
    }
    pairs = []
    for obj in objects:
        if obj["kind"] != "Deployment":
            continue
        env = container_env(obj)
        urls = [v for k, v in env.items() if k.endswith("_DATABASE_URL") and isinstance(v, str)]
        for url in urls:
            match = URL.search(url)
            assert match, f"{obj['metadata']['name']}: {url} does not take DB_USER from its Secret"
            release = release_of(obj)
            secret = secrets[(release, obj["metadata"]["name"])]
            pairs.append((release, match.group(1), secret.get("DB_USER", "")))
    return pairs


def _mismatches(objects: list[dict]) -> list[str]:
    pairs = _pairs(objects)
    assert pairs, "no release reads a database URL"
    return [f"{r}: database {db}, DB_USER {user!r}" for r, db, user in pairs if db != user]


def test_every_example_release_logs_in_as_its_databases_owner(helm_copy: Path) -> None:
    assert _mismatches(_render(helm_copy)) == []


def test_every_pilot_release_logs_in_as_its_databases_owner(
    render_pilot: Callable[..., PilotRender],
) -> None:
    objects = render_pilot().ok()
    # Participant registries included: the release that had it wrong.
    assert any(
        r.startswith("ds-identity-registry-") for r, _, _ in _pairs(objects)
    ), "no participant registry in the pilot render"
    assert _mismatches(objects) == []
