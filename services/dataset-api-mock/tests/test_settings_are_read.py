"""Every `Settings` field must be read by something.

Ported from `services/connector`, via `identity-registry`, `provenance` and
`federated-catalog`. It is the only test in this unit that can fail because of
something a change *did not* do: a setting added and then never wired shows up
here rather than in a review.

It is here because of `DATASET_API_ENFORCE_CONSENT`. It was declared, defaulted
to `true`, set explicitly in `docker-compose.rec.yml` and documented in
`.env.example` — and read by nothing. Three places said this PEP's consent
enforcement was a configurable switch; no code anywhere consulted it. The
dangerous half is not the dead line, it is the belief: an operator turning it
"on" during an incident would have changed nothing, and would have been told so
by no one.
"""

from __future__ import annotations

import pathlib
import re

from dataset_api_mock.main import Settings

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "dataset_api_mock"
REPO = pathlib.Path(__file__).resolve().parents[3]

# Read by the pydantic-settings machinery itself, never by our code.
_FRAMEWORK_FIELDS: set[str] = set()


def _sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py"))


def test_every_settings_field_is_read():
    body = _sources()
    unread = [
        name
        for name in Settings.model_fields
        if name not in _FRAMEWORK_FIELDS and f"settings.{name}" not in body
    ]
    assert not unread, (
        f"Settings fields nothing reads: {unread}. Wire them or delete them — a "
        "setting that is declared and not read is configuration a deployment can "
        "set with no effect, and a control an operator can believe in."
    )


def test_no_scope_name_is_configurable():
    """A permission is vocabulary. It is declared in `clients.yaml` and named
    literally at the guard; making it an env var lets a deployment widen what the
    service accepts without any guard changing."""
    scopeish = [n for n in Settings.model_fields if n.endswith("_scope")]
    assert not scopeish, f"scope names must not be settings: {scopeish}"


def _deployment_tokens(prefix: str):
    """Every `{PREFIX}*` name a deployment file declares, with where it came from.

    A declaration is `NAME=` or `NAME:` — a leading `#` is stripped first, so a
    commented-out alternative still counts (that is how `.env.example` documents
    one), but a sentence in prose that happens to open with a variable name does
    not. This unit is where the sweep was written, and until issue #17 it split
    on `=`/`:` without anchoring: the four units ported from it anchored, so the
    copy named as the reference was the weaker one. This is their parser.
    """
    pattern = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)\s*[:=]")
    for path in [REPO / ".env.example", *sorted(REPO.glob("docker-compose*.yml"))]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line.strip())
            if match and match.group(1).startswith(prefix):
                yield path.name, match.group(1)


def test_no_deployment_file_sets_a_variable_this_service_does_not_read():
    """The other direction, and the one that made the dead setting convincing.

    A field can be deleted from `config.py` while `docker-compose` and
    `.env.example` keep advertising it. Both files are the deployment's view of
    what this service can be told, so a name in them that reaches nothing is a
    documented control that does not exist.
    """
    declared = {f"DATASET_API_{name.upper()}" for name in Settings.model_fields}
    # Read by compose and the Dockerfile rather than by this service's Settings.
    known_elsewhere = {"DATASET_API_MOCK_PORT", "DATASET_API_PATH", "DATASET_API_URL"}

    stray = sorted(
        f"{where}: {token}"
        for where, token in _deployment_tokens("DATASET_API_")
        if token not in declared and token not in known_elsewhere
    )
    assert not stray, (
        f"Deployment files name settings this service does not read: {stray}"
    )
