"""No partner, pilot or private-deployment name is committed to this repository.

This repository is public. Naming CELINE as a project, and linking CELINE's public
open-source repositories, is fine. Naming a pilot or partner organisation, a real
member id, a private deployment's hostname, a private dataset or a private repository
is not: those use the generic stand-ins (``example-rec``, ``example-dso``,
``rec.example.org``, ``ex-00001``) instead.

**No denylist is committed.** A list of the names it guards against - in any form,
hashed or not - would itself be the leak. Terms are normalised (lower case, every
character outside ``[a-z0-9]`` removed), so one term covers every spelling that
differs only in case or separators, and runs of up to four adjacent words are
checked the same way. Without a local list the guard is skipped, never passed.

**A local plain-text list** can extend it on one machine without committing anything:
one term per line in the file named by ``DS_PRIVATE_NAMES_FILE``, or in
``.private-names`` at the repository root (gitignored). Lines starting with ``#``
are comments.

The scan reads every file git would commit (tracked, plus untracked-but-not-ignored),
so a leak fails here before it is committed, not after.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(os.environ.get("DS_NAMES_ROOT") or Path(__file__).resolve().parents[3])

#: Nothing is committed here: a list of the names would itself be the leak.
#: Terms come only from the local list (see the module docstring).
DENIED: dict[str, int] = {}

#: Member-id prefixes, likewise never committed.
DENIED_ID_PREFIXES: frozenset[str] = frozenset()

#: Runs of up to this many adjacent words are joined and checked.
MAX_WORDS = 4

WORD = re.compile(r"[A-Za-z0-9]+")
MEMBER_ID = re.compile(r"\b([A-Za-z]{2,4})-\d{3,}\b")
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".jar"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".gradle", "build", ".svelte-kit"}


def normalise(term: str) -> str:
    return re.sub(r"[^a-z0-9]", "", term.lower())


def sha(term: str) -> str:
    return hashlib.sha256(term.encode()).hexdigest()


def local_terms() -> dict[str, int]:
    path = Path(os.environ.get("DS_PRIVATE_NAMES_FILE") or REPO / ".private-names")
    if not path.is_file():
        return {}
    terms = (
        normalise(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    return {sha(t): len(t) for t in terms if t}


def candidate_files(root: Path) -> list[Path]:
    """What git would commit; a plain walk where there is no git (a copied tree)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.decode()
        paths = [root / p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        paths = [
            p
            for p in root.rglob("*")
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(root).parts)
        ]
    return [p for p in paths if p.is_file() and p.suffix.lower() not in SKIP_SUFFIXES]


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.text.strip()[:160]}"


def scan_text(text: str, denied: dict[str, int], id_prefixes: frozenset[str]) -> list[int]:
    """Line numbers (1-based) carrying a denied term."""
    lengths = set(denied.values())
    hits: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        words = [w.lower() for w in WORD.findall(line)]
        found = False
        for i in range(len(words)):
            joined = ""
            for word in words[i : i + MAX_WORDS]:
                joined += word
                if len(joined) in lengths and sha(joined) in denied:
                    found = True
                    break
            if found:
                break
        if not found:
            found = any(sha(m.group(1).lower()) in id_prefixes for m in MEMBER_ID.finditer(line))
        if found:
            hits.append(number)
    return hits


def scan(root: Path) -> list[Hit]:
    denied = {**DENIED, **local_terms()}
    hits: list[Hit] = []
    for path in candidate_files(root):
        rel = path.relative_to(root).as_posix()
        if scan_text(rel, denied, DENIED_ID_PREFIXES):
            hits.append(Hit(rel, 0, "(the path itself)"))
        raw = path.read_bytes()
        if b"\0" in raw[:8192]:
            continue
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        hits.extend(Hit(rel, n, lines[n - 1]) for n in scan_text(text, denied, DENIED_ID_PREFIXES))
    return hits


def test_no_private_name_is_committed() -> None:
    if not DENIED and not local_terms():
        pytest.skip("skipped: no local list (DS_PRIVATE_NAMES_FILE or .private-names)")
    hits = scan(REPO)
    assert not hits, (
        "a partner, pilot or private-deployment name is in the tree; replace it with a "
        "generic stand-in (example-rec, example-dso, rec.example.org, ex-00001):\n"
        + "\n".join(str(h) for h in hits)
    )


def test_every_spelling_of_a_term_is_one_entry() -> None:
    denied = {sha("foobar"): 6}
    for spelling in ("foobar", "FooBar", "foo bar", "foo-bar", "foo_bar", "x.Foo.Bar.y"):
        assert scan_text(spelling, denied, frozenset()) == [1], spelling
    assert scan_text("foo\nbar", denied, frozenset()) == []
    assert scan_text("foobarbaz", denied, frozenset()) == []


def test_a_member_id_is_caught_by_its_prefix_and_the_generic_one_is_not() -> None:
    prefixes = frozenset({sha("zz")})
    assert scan_text("member zz-00012 enrolled", {}, prefixes) == [1]
    assert scan_text("member ex-00001 enrolled", {}, prefixes) == []


def test_no_denylist_is_committed() -> None:
    assert not DENIED
    assert not DENIED_ID_PREFIXES
