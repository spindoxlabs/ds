"""AUTH-03 · what the package imports, it declares.

Two third-party packages were imported at module level and not in
``[project].dependencies``:

- ``httpx``, by ``service_token.ServiceTokenProvider`` — ``dev``-only, so the
  provider four services import was unimportable from a plain install, and only
  the test venv ever proved otherwise;
- ``fastapi``, by ``user_credentials.py`` — an *optional extra* named in no
  Dockerfile and no pyproject, while the module raises ``HTTPException`` from 24
  call sites.

Neither was caught by any suite, because a test venv installs the ``dev`` extra
and every service installs FastAPI for its own reasons. The failure mode is a
clean production image that ``ImportError``s on the first request that needs a
service token — which is what makes this a startup invariant (`T-4`) rather than
a packaging tidy-up.
"""
from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
SRC = UNIT / "src" / "ds_auth"

#: Distribution name per import name, where they differ.
DIST_OF_MODULE = {"jwt": "pyjwt", "yaml": "pyyaml"}


def _declared() -> set[str]:
    meta = tomllib.loads((UNIT / "pyproject.toml").read_text())
    names = set()
    for spec in meta["project"]["dependencies"]:
        # "pyjwt[crypto]>=2.9" -> "pyjwt"
        names.add(spec.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower())
    return names


def _module_level_imports(path: Path) -> set[str]:
    """Top-level imports only.

    A deferred import inside a function is a deliberate optional dependency —
    `ds_auth/__init__.py` does exactly that for `ServiceTokenProvider` — and this
    check must not turn that pattern into an error.
    """
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def _third_party(names: set[str]) -> set[str]:
    return {
        n for n in names
        if n not in sys.stdlib_module_names and n != "ds_auth"
    }


MODULES = sorted(SRC.glob("*.py"))


def test_the_search_found_the_package():
    assert len(MODULES) > 8, f"only {len(MODULES)} modules found under {SRC}"


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_every_module_level_import_is_a_declared_dependency(module):
    declared = _declared()
    for name in sorted(_third_party(_module_level_imports(module))):
        dist = DIST_OF_MODULE.get(name, name).lower()
        assert dist in declared, (
            f"{module.name} imports {name!r} at module level, but {dist!r} is not "
            f"in [project].dependencies. Declared: {sorted(declared)}"
        )


def test_the_two_that_were_missing_are_declared():
    """Named explicitly, so the row is legible from the test that closes it."""
    declared = _declared()
    assert "httpx" in declared
    assert "fastapi" in declared


def test_no_extra_promises_a_dependency_the_package_already_requires():
    """The `fastapi` extra claimed FastAPI was optional while a core module
    imported it. Nothing named the extra, so it documented a choice that did not
    exist."""
    meta = tomllib.loads((UNIT / "pyproject.toml").read_text())
    extras = meta["project"].get("optional-dependencies", {})
    assert "fastapi" not in extras
