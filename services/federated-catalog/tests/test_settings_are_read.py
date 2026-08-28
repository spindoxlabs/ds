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

import re

import pathlib

from federated_catalog.config import Settings

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "federated_catalog"
#: The repository root — `.env.example` and the compose files live there.
REPO = pathlib.Path(__file__).resolve().parents[3]

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

#: `CATALOG_*` names a deployment file carries and this service does not read.
#: Empty, and that is the healthy state: an entry is an exemption from the sweep
#: below, so each one would have to name its actual reader.
READ_BY_SOMETHING_ELSE: set[str] = set()


def _deployment_tokens(prefix: str):
    """Every `{PREFIX}*` name a deployment file declares, with where it came from.

    A declaration is `NAME=` or `NAME:` — a leading `#` is stripped first, so a
    commented-out alternative still counts (that is how `.env.example` documents
    one), but a sentence in prose that happens to open with a variable name does
    not. The `dataset-api-mock` copy this was ported from split on `=`/`:`
    without anchoring, and picked up comment text as declarations; it was
    brought in line with this parser in issue #17.
    """
    pattern = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)\s*[:=]")
    for path in [REPO / ".env.example", *sorted(REPO.glob("docker-compose*.yml"))]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line.strip())
            if match and match.group(1).startswith(prefix):
                yield path.name, match.group(1)


def test_no_deployment_file_names_a_variable_this_service_does_not_read():
    """The `.env.example` → code direction (`ENV-01`/`ENV-05`, issue #9).

    `.env.example` opens by claiming it "documents *every* environment variable
    the platform reads", and until 2026-08-28 one unit checked that claim — the
    mock, whose sweep swept both ways. Every other unit checked only that a
    declared `Settings` field is read, which cannot see the opposite rot: a field
    deleted from `config.py` while `.env.example`, a compose file, a chart value
    and a Secret key go on advertising it.

    That is how `DATASET_API_ENFORCE_CONSENT` survived — declared, defaulted
    `true`, set in compose, documented, and consulted by no code anywhere. The
    dangerous half is the belief, not the dead line: an operator turning it "on"
    during an incident would have changed nothing and been told so by nobody.
    """
    prefix = Settings.model_config.get("env_prefix", "")
    assert prefix, "this test needs an env_prefix to know what to sweep"
    declared = {f"{prefix}{name.upper()}" for name in Settings.model_fields}

    stray = sorted(
        f"{where}: {token}"
        for where, token in _deployment_tokens(prefix)
        if token not in declared and token not in READ_BY_SOMETHING_ELSE
    )
    assert not stray, (
        f"deployment files name {prefix}* variables this service does not read: "
        f"{stray}. Either wire the setting, delete the declaration, or — if "
        "another component genuinely reads it — name it in "
        "READ_BY_SOMETHING_ELSE with the reader."
    )
