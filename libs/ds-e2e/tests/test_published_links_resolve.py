"""Every published docs URL a README points at must exist in `docs/`.

**Why this lives here.** The invariant spans every unit's `README.md` and the
whole of `docs/`, so it belongs to none of them — the same argument
`test_build_covers_every_stack.py` makes, and `libs/ds-e2e` runs in CI.

**The defect, three times.** `GOV-16` found four READMEs linking
`…/governance-and-odrl/`, a page that has never existed, and re-pointed them.
`DOC-01` then found **eight more dead paths in nineteen places** — `/architecture/`,
`/consent-and-sovereignty/`, `/identity-and-dcp/` and five others — still 404 on
the live site. The main `README.md` carried four of them in its own navigation
table.

The reason it kept happening is worth stating, because it is not carelessness:
`mkdocs build --strict` validates links **inside** `docs/`, so a relative link
from one page to another cannot rot. Nothing validated the **absolute** URLs
that files *outside* `docs/` point back at it with. Those are the ones a reader
on GitHub clicks first, and they were the only ones nobody checked.

**Offline by construction.** It resolves each URL to the file that would serve it
rather than fetching it — `ds-e2e`'s unit suite refuses to open a socket at all
(`tests/conftest.py`, `E2E-17`), and a link check that needs the network is one
that gets skipped in CI and stops running. The mapping is mkdocs' own, from
`awesome-pages`: a URL path is a file path, and a trailing slash means either
`<name>.md` or `<name>/index.md`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"

SITE_URL = "https://spindoxlabs.github.io/ds/"

#: Served by `hooks/publish_schemas.py` from the repository root, not from
#: `docs/` — the generated schemas declare this URL as their own `$id`, so it has
#: to serve the document itself.
SCHEMA_PREFIX = "schemas/"

#: Markdown outside `docs/` — the files a reader meets on GitHub.
def _markdown_files() -> list[Path]:
    skip = {"node_modules", ".venv", "site", "data", ".git"}
    return [
        p
        for p in ROOT.rglob("*.md")
        if DOCS not in p.parents and not skip & set(p.relative_to(ROOT).parts)
    ]


def _links(text: str) -> set[str]:
    """Every published-site URL in *text*, as a path relative to the site root."""
    found = set()
    for raw in re.findall(rf"{re.escape(SITE_URL)}[A-Za-z0-9./_-]*", text):
        path = raw[len(SITE_URL) :]
        # Markdown often ends a sentence right after the link.
        found.add(path.rstrip(".,);:"))
    return found


def _candidates(path: str) -> list[Path]:
    """Files that could serve *path*, in the order mkdocs would consider them."""
    if path.startswith(SCHEMA_PREFIX):
        return [ROOT / path]
    if path in ("", "/"):
        return [DOCS / "index.md"]
    stem = path.rstrip("/")
    return [DOCS / f"{stem}.md", DOCS / stem / "index.md"]


def _all_links() -> list[tuple[Path, str]]:
    pairs = []
    for f in _markdown_files():
        for link in _links(f.read_text(encoding="utf-8")):
            pairs.append((f, link))
    return sorted(pairs, key=lambda p: (str(p[0]), p[1]))


LINKS = _all_links()


def test_there_are_links_to_check():
    """Guard the guard.

    A regex that quietly stopped matching would make every assertion below pass
    over an empty list — `E2E-01`'s `all([]) == True`, in a different file. The
    READMEs link to the site heavily; zero means the extraction broke, not that
    the links went away.
    """
    assert len(LINKS) > 10, (
        f"only {len(LINKS)} published links found across {len(_markdown_files())} "
        "markdown files — the extraction is probably broken, not the READMEs"
    )


@pytest.mark.parametrize(
    "source,link",
    LINKS,
    ids=[f"{src.relative_to(ROOT)}→/{url}" for src, url in LINKS],
)
def test_every_published_link_has_a_page(source: Path, link: str):
    """A link to the docs site must name a page the site builds.

    Fails on the *source* file, so the message says which README to edit rather
    than which page is missing — the fix is almost always re-pointing the link,
    not writing the page.
    """
    candidates = _candidates(link)
    assert any(c.exists() for c in candidates), (
        f"{source.relative_to(ROOT)} links to {SITE_URL}{link}, which the site "
        f"does not serve — none of {[str(c.relative_to(ROOT)) for c in candidates]} "
        f"exists.\n\nRe-point the link at a page that does. `mkdocs build "
        f"--strict` cannot catch this: it validates links *inside* docs/, and "
        f"this one points at docs/ from outside it."
    )
