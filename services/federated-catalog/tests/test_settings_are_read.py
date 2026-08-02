"""Every `Settings` field must be read by something.

Ported from `services/connector`, via `services/identity-registry` and
`services/provenance`. It is the only test in this unit that can fail because of
something a change *did not* do: a setting added to `config.py` and then never
wired shows up here rather than in a review.

The failure mode it exists for is not cosmetic. `read_scope: str = "catalog.read"`
looked like the guard's source of truth and was not — `dependencies.py` names the
scope literally — so a deployment setting `CATALOG_READ_SCOPE` would have changed
nothing while appearing to change what the service accepts. A scope name is
vocabulary, not configuration.
"""
from __future__ import annotations

import pathlib

from federated_catalog.config import Settings

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "federated_catalog"

# Read by the pydantic-settings machinery itself, never by our code.
_FRAMEWORK_FIELDS: set[str] = set()


def _sources() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in SRC.rglob("*.py")
        if p.name != "config.py"
    )


def test_every_settings_field_is_read():
    body = _sources()
    unread = [
        name
        for name in Settings.model_fields
        if name not in _FRAMEWORK_FIELDS and f"settings.{name}" not in body
        and f".{name}" not in body
    ]
    assert not unread, (
        f"Settings fields nothing reads: {unread}. Wire them or delete them — "
        "a setting that is declared and not read is configuration a deployment "
        "can set with no effect."
    )


def test_no_scope_name_is_configurable():
    """A permission is vocabulary. It is declared in `clients.yaml` and named
    literally at the guard; making it an env var lets a deployment widen what the
    service accepts without any guard changing."""
    scopeish = [n for n in Settings.model_fields if n.endswith("_scope")]
    assert not scopeish, f"scope names must not be settings: {scopeish}"
