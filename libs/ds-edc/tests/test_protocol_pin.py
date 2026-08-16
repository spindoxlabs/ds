"""EDCL-02 · the protocol pin, checked against the repository that carries it.

`DATASPACE_PROTOCOL` occurred once and was compared with nothing, so the row
asked for it to be checked against *something*. The rulebook says what:

- data exchange §6 rule 2 — *"the version pin lives in exactly one place
  (`libs/ds-edc/src/ds_edc/schemas.py`); changing it anywhere else is a defect"*;
- data exchange X-2 — *"a participant advertising a DSP endpoint without the
  `/2025-1` suffix is not reachable"*, recorded as **partly** enforced, with
  three configuration files documenting the URL without it (defect P2-2).

So the check is: every DSP address configured anywhere in the tree carries the
version this file pins, derived from the pin rather than written out again. This
is the `T-4` shape — a startup invariant, hoisted to a test — and it is the one
thing that makes bumping the version a mechanical change instead of a hunt.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ds_edc.schemas import DATASPACE_PROTOCOL, DSP_PATH_SEGMENT, DSP_VERSION

REPO = Path(__file__).resolve().parents[3]

#: Where a DSP address is *configured*. Prose in `docs/` is excluded: it
#: discusses versions, including old ones, and is not what a connector dials.
SEARCH = (
    ("", "docker-compose*.yml"),
    ("", ".env.example"),
    ("", ".env.local"),
    ("helm", "**/*.yaml"),
    ("libs", "*/src/**/*.py"),
    ("services", "*/src/**/*.py"),
    ("services", "*/*/src/**/*.java"),
)

SKIP_PARTS = {"node_modules", ".svelte-kit", "__pycache__", ".git", "data", "build"}

#: A setting whose value *is* a DSP endpoint. Matched on the name, so a new one
#: is covered the day it is added rather than the day someone remembers.
DSP_SETTING = re.compile(
    r"^[^\S\n]*[-\"']?\s*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*(DSP_ADDRESS|COUNTER_PARTY_ADDRESS|PROTOCOL_URL|DSP_ENDPOINT))"
    r"\s*[:=]\s*[\"']?(?P<value>https?://\S+?)[\"',]?\s*$",
    re.MULTILINE,
)

#: Any URL that already declares itself a protocol endpoint by its path.
PROTOCOL_URL = re.compile(r"https?://[^\s\"'`,)\]}]*?/protocol/[0-9][^\s\"'`,)\]}]*")


def _files():
    seen = set()
    for root, pattern in SEARCH:
        base = REPO / root if root else REPO
        for path in sorted(base.glob(pattern)):
            if not path.is_file() or set(path.parts) & SKIP_PARTS:
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO))


@pytest.mark.rule("X-2")
def test_the_version_is_derived_from_the_pin_and_not_written_twice():
    assert DATASPACE_PROTOCOL == f"dataspace-protocol-http:{DSP_VERSION}"
    assert DSP_PATH_SEGMENT == f"/protocol/{DSP_VERSION}"


@pytest.mark.rule("X-2")
def test_the_pin_occurs_once_in_the_tree():
    """§6 rule 2. A second copy is how the two come to disagree."""
    holders = [
        _rel(p) for p in _files()
        if DATASPACE_PROTOCOL in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert holders == ["libs/ds-edc/src/ds_edc/schemas.py"], (
        f"the protocol pin is declared in {holders}; the rulebook makes ds-edc "
        "its only home"
    )


@pytest.mark.rule("X-1", "X-2")
def test_every_configured_dsp_address_carries_the_pinned_version():
    """X-2, as a check rather than as a claim.

    A DSP address without the version segment is not reachable — EDC serves the
    protocol context under the versioned path — so this is a connectivity
    failure that only shows up at negotiation time, on whichever counterparty
    was configured from the file that omitted it.
    """
    wrong = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in DSP_SETTING.finditer(text):
            value = m.group("value").rstrip("/")
            if not value.endswith(DSP_PATH_SEGMENT):
                line = text[: m.start()].count("\n") + 1
                wrong.append(
                    f"{_rel(path)}:{line} {m.group('name')}={m.group('value')}"
                )
    assert not wrong, (
        "DSP addresses missing "
        f"{DSP_PATH_SEGMENT!r}:\n  " + "\n  ".join(wrong)
    )


@pytest.mark.rule("X-2")
def test_no_protocol_url_names_a_different_version():
    """The other direction: a URL that *has* a version segment, and it is stale.

    Catches the half of a version bump that gets missed — the addresses left on
    the old version, which fail as "counterparty unreachable" rather than as
    "wrong protocol version".
    """
    wrong = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in PROTOCOL_URL.finditer(text):
            url = m.group(0).rstrip("/*")
            segment = url.split("/protocol/", 1)[1].split("/")[0]
            if segment != DSP_VERSION:
                line = text[: m.start()].count("\n") + 1
                wrong.append(f"{_rel(path)}:{line} {m.group(0)}")
    assert not wrong, (
        f"protocol URLs on a version other than {DSP_VERSION!r}:\n  "
        + "\n  ".join(wrong)
    )


@pytest.mark.parametrize("body", [
    {"counter_party_address": "http://172.17.0.1:19194/protocol/2025-1"},
])
@pytest.mark.rule("X-2")
def test_the_search_actually_reaches_the_tree(body):
    """A guard on this file, not on the platform.

    A glob that matches nothing makes the three tests above pass by finding
    nothing to check — the exact failure mode `.agents/ledger.md` closes with:
    *a green check is not a check that ran.*
    """
    files = list(_files())
    assert len(files) > 20, f"only {len(files)} files searched"
    names = {_rel(p) for p in files}
    assert "docker-compose.rec.yml" in names
    assert "libs/ds-e2e/src/ds_e2e/config.py" in names
    assert any(n.startswith("helm/") for n in names)
    assert PROTOCOL_URL.search(body["counter_party_address"])
