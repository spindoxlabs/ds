"""Every `Settings` field is read by something outside `config.py`.

Ported from `services/connector`, which carried seven settings nothing read.
This unit's own ledger row named five candidates; the sweep is what decides
which of them are real, and — more usefully — what keeps the next one from
arriving.

A configuration surface that answers is worse than one that is absent. A field
called `read_scope` reads like it can rename the scope a caller must hold; if
the guard checks a literal instead, an operator who sets
`IDENTITY_REGISTRY_READ_SCOPE` gets silence and no warning that the value went
nowhere. This is the only test in the unit that can fail because of something a
change *did not* do.
"""

from __future__ import annotations

import re
from pathlib import Path

from identity_registry.config import Settings

SRC = Path(__file__).resolve().parents[1] / "src" / "identity_registry"
#: The repository root — `.env.example` and the compose files live there.
REPO = Path(__file__).resolve().parents[3]

#: Fields whose reader is not a ``settings.<name>`` expression. Each needs a
#: reason — an entry here is an exemption from the rule above, not a parking
#: space for the next dead setting.
READ_ELSEWHERE: dict[str, str] = {
    "identity_registry_public_url": (
        "read by `Settings.public_base_url` in config.py, which is what the rest "
        "of the service uses. Deriving the URL in one place is the point: six "
        "call sites used to build the StatusList URL by hand, and every one of "
        "them ignored this setting"
    ),
    "trust_anchor_url": (
        "read by `Settings.issuer_base_url` in config.py, the same shape as "
        "`identity_registry_public_url` above. The fallback it needs — the "
        "anchor's did:web host, over whichever scheme `did_web_use_https` "
        "selects — belongs beside the setting rather than at the one call site, "
        "so that a production instance cannot enrol over plain HTTP by omission"
    ),
}

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

#: `IDENTITY_REGISTRY_*` names a deployment file carries and this service does
#: not read. Each needs its actual reader — an entry here is an exemption from
#: the sweep below, not somewhere to park a dead name.
READ_BY_SOMETHING_ELSE = {
    # This service's *address*, read by its callers: the portal server-side
    # (`lib/server/identity-registry.ts`) and `ds_e2e.config`. Not a setting of
    # the registry itself.
    "IDENTITY_REGISTRY_URL",
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
