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
