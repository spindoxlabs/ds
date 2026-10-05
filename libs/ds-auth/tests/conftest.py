"""The suite declares its own environment; it does not inherit one.

`ds_auth.production.current_env()` defaults to `production` when `DS_ENV` is
unset, and `verify_user_vc_jwt` reads it to decide whether a credential may be
accepted with no status source. So a suite that left the variable to the shell
would answer differently under `task test` and a bare `pytest`. An assignment,
not `setdefault`, so an exported `DS_ENV=production` cannot change the result
either. Production behaviour is asserted per test, with `monkeypatch`.
"""

import os

os.environ["DS_ENV"] = "dev"
