"""The suite states its own `DS_ENV`, so the same tree gives one answer.

`ds_auth.production.current_env()` defaults to `production` when `DS_ENV` is
unset, and `create_app`'s lifespan builds a `ProductionGuard` from it. Every
test that enters that lifespan was therefore asking the shell what environment
it was in, and the same commit answered differently depending on how pytest was
started:

* `task -d services/connector test` — the task's `env:` block supplied
  `DS_ENV=dev` — `603 passed`;
* `uv run pytest tests/` in the same directory — `DS_ENV` unset, so the guard
  armed — `2 failed, 601 passed`, both `InsecureProductionConfig`.

`tests/conftest.py` now pins it, before `connector.main` is imported. These
tests are what makes removing that pin visible: a run with no `DS_ENV` in the
environment fails here first, and names the line to restore.

The pin is an **assignment**, not a `setdefault`: hermetic means the answer does
not move when the shell says `DS_ENV=production` either, and `setdefault` would
leave exactly that hole open. Production behaviour is asserted where it belongs,
in `libs/ds-auth/tests/test_production.py`, per test and with `monkeypatch`.
"""

from __future__ import annotations

import os
from pathlib import Path

from ds_auth.production import current_env, is_production

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")


def test_the_suite_runs_as_dev_whatever_the_shell_says():
    """Fails the moment the pin in `conftest.py` stops taking effect."""
    assert os.environ.get("DS_ENV") == "dev", (
        "the connector suite must declare DS_ENV=dev itself — restore the pin "
        "at the top of tests/conftest.py"
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
