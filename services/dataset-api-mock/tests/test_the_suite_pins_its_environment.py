"""The suite states its own `DS_ENV`, so the same tree gives one answer.

`ds_auth.production.current_env()` defaults to `production` when `DS_ENV` is
unset, and this service builds a `ProductionGuard` at import. The same commit
answered differently depending on how pytest was started:

* `task -d services/dataset-api-mock test` — the task's `env:` block supplied
  `DS_ENV=dev` — `79 passed`;
* `uv run pytest` in the same directory — `DS_ENV` unset, so the guard armed —
  `7 errors`, every one an `InsecureProductionConfig` raised during collection.

`tests/conftest.py` pins it now. These tests are what makes removing that pin
visible. The connector suite carries the same pair for the same reason.
"""

from __future__ import annotations

import os
from pathlib import Path

from ds_auth.production import current_env, is_production

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")


def test_the_suite_runs_as_dev_whatever_the_shell_says():
    """Fails the moment the pin in `conftest.py` stops taking effect."""
    assert os.environ.get("DS_ENV") == "dev", (
        "this suite must declare DS_ENV=dev itself — restore the pin in tests/conftest.py"
    )
    assert current_env() == "dev"
    assert is_production() is False


def test_the_pin_overrides_the_shell_rather_than_deferring_to_it():
    """`setdefault` would make an exported `DS_ENV=production` break the suite.

    Asserted against the source because the difference is invisible at runtime
    in the shell where it does not matter — which is the shell a regression
    would be introduced in.
    """
    assert 'os.environ["DS_ENV"] = "dev"' in CONFTEST
    assert 'setdefault("DS_ENV"' not in CONFTEST
