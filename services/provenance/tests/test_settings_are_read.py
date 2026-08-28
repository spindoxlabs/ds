"""Every `Settings` field is read by something outside `config.py`.

Ported from `services/connector` via `services/identity-registry`, both of which
carried settings nothing read. Here it names three: `read_scope`, `write_scope`
and `base_url`.

A configuration surface that answers is worse than one that is absent. A field
called `write_scope` reads like it can rename the permission a caller must hold;
`dependencies.py` checks the literal `"provenance.write"` instead, so an operator
who sets `PROVENANCE_WRITE_SCOPE` gets silence — and a guard and a realm that
disagree about what a caller must present. This is the only test in the unit that
can fail because of something a change *did not* do.
"""

from __future__ import annotations

import re
from pathlib import Path

from provenance.config import Settings

SRC = Path(__file__).resolve().parents[1] / "src" / "provenance"
#: The repository root — `.env.example` and the compose files live there.
REPO = Path(__file__).resolve().parents[3]

#: Fields whose reader is not a ``settings.<name>`` expression. Each needs a
#: reason — an entry here is an exemption from the rule above, not a parking
#: space for the next dead setting.
READ_ELSEWHERE: dict[str, str] = {}

#: ``settings.name``, or the name quoted — a `getattr` is a read like any
#: other, and the production guard names its variables as strings.
_READ = r'\.{name}\b|["\']{name}["\']'

_COMMENT = re.compile(r"#.*$", re.MULTILINE)


def _sources() -> str:
    """Every module but `config.py`, with comments stripped.

    Comments are removed deliberately: `config.py`'s siblings discuss settings
    in prose, and a setting mentioned in a comment is not a setting anybody
    reads.
    """
    return _COMMENT.sub(
        "",
        "\n".join(
            p.read_text(encoding="utf-8")
            for p in SRC.rglob("*.py")
            if p.name != "config.py"
        ),
    )


def test_no_setting_is_read_by_nothing():
    body = _sources()
    unread = [
        name
        for name in Settings.model_fields
        if name not in READ_ELSEWHERE
        and not re.search(_READ.format(name=re.escape(name)), body)
    ]
    assert unread == [], (
        "settings read by nothing outside config.py — delete them, or wire them: "
        f"{unread}"
    )

#: `PROVENANCE_*` names a deployment file carries and this service does not
#: read. Each needs its actual reader — an entry here is an exemption from the
#: sweep below, not somewhere to park a dead name.
READ_BY_SOMETHING_ELSE = {
    # Role-suffixed pair. The Taskfile and compose choose one and pass it as the
    # unsuffixed variable this service reads.
    "PROVENANCE_DATABASE_URL_PROVIDER",
    "PROVENANCE_DATABASE_URL_CONSUMER",
    # This service's *address*, read by the portal server-side
    # (`lib/server/provenance.ts` and the health page). Not a setting of it.
    "PROVENANCE_URL",
}


def _deployment_tokens(prefix: str):
    """Every `{PREFIX}*` name a deployment file declares, with where it came from.

    A declaration is `NAME=` or `NAME:` — a leading `#` is stripped first, so a
    commented-out alternative still counts (that is how `.env.example` documents
    one), but a sentence in prose that happens to open with a variable name does
    not. The reference implementation split on `=`/`:` without anchoring, and
    picked up comment text as declarations.
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
