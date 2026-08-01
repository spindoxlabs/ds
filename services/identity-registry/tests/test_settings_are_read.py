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
