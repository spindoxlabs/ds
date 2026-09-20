"""Shared test setup for the reference data plane.

**The suite declares its own environment; it does not inherit one.**

`ds_auth.production.current_env()` defaults to `production` when `DS_ENV` is
unset — deliberately, so a deployment that forgets the variable fails closed.
The cost is that a test importing an app which builds a `ProductionGuard` asks
the *shell* what environment it is in. `task -d services/dataset-api-mock test`
used to supply `DS_ENV=dev` from its own `env:` block, so the same tree answered
`79 passed` through the task and `7 errors` — `InsecureProductionConfig`, at
collection — under a bare `uv run pytest`. A suite whose answer depends on who
invoked it is not evidence of anything.

The pin lives here, where every invocation route passes, and it is an assignment
rather than a `setdefault`: a `DS_ENV=production` exported in the shell must not
change the result either. This is the only pin — the task no longer sets one, so
deleting this line fails the suite rather than only the runs nobody makes.
`test_the_suite_pins_its_environment.py` asserts it.

Production *behaviour* is not tested by pretending this suite is production:
`libs/ds-auth/tests/test_production.py` owns that, per test, with `monkeypatch`.
"""

from __future__ import annotations

import os

os.environ["DS_ENV"] = "dev"
