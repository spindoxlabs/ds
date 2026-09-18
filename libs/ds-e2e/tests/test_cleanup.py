"""Tests for cleanup module.

**These tests used to clean the developer's running stack** (`E2E-17`).
`run_cleanup` built its own `httpx.Client`, so mocking `psycopg` and
`HttpClient` left the EDC Management API calls live: eight green assertions
here deleted every contract definition and policy from both providers' EDCs.
`conftest.py` refuses any socket in this suite so the next such path fails
loudly. The management calls themselves are gone now: the port is not
published, and the database reset is what empties the stores.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ds_e2e.cleanup import (
    DATABASES,
    EDC_DATABASES,
    CleanupIncomplete,
    provider_sync_targets,
    run_cleanup,
)
from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient


def test_cleanup_truncates_databases():
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {"Authorization": "Bearer tok"}
    http.post.return_value = {}

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch(
        "ds_e2e.cleanup.psycopg.connect", return_value=mock_conn
    ) as mock_connect:
        run_cleanup(settings, http)

    # One connection per application database it truncates, plus one to the
    # `postgres` database per EDC store it drops and recreates.
    assert mock_connect.call_count == len(DATABASES) + len(EDC_DATABASES)
    # One TRUNCATE per application database; a session terminate, a DROP and a
    # CREATE per EDC store. The terminate is not optional and not incidental:
    # the three EDC control planes hold pools against those databases, and
    # without it PostgreSQL refuses the DROP and the clean silently leaves the
    # previous run's agreements in place.
    assert mock_cursor.execute.call_count == len(DATABASES) + 3 * len(EDC_DATABASES)
    executed = [c.args[0] for c in mock_cursor.execute.call_args_list]
    assert sum("pg_terminate_backend" in sql for sql in executed) == len(EDC_DATABASES)
    # **The clean makes no HTTP call at all** (2026-09-18). It used to re-sync
    # both providers here, which could never have worked: an EDC runs its schema
    # migration at boot, so at that point every control plane was talking to a
    # database with no tables and every write answered 500. It *looked* fine
    # because `POST /provider/sync` answered 200 with everything in `errors`.
    # The publish that works is `task e2e:sync-providers`, after the restart.
    assert http.post.call_count == 0


def test_cleanup_continues_on_db_error():
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {"Authorization": "Bearer tok"}
    http.post.return_value = {}

    import psycopg

    with patch(
        "ds_e2e.cleanup.psycopg.connect",
        side_effect=psycopg.Error("connection refused"),
    ):
        # **Continues, and then reports.** "Continues" is about not
        # short-circuiting the rest of the clean — it was never about staying
        # quiet. A reset that did not happen used to warn and return normally,
        # so `e2e:prepare` went on to run every flow against the previous run's
        # EDC agreements; two flows were then denied in `policy.monitor`,
        # correctly, and read as product failures for a session.
        with pytest.raises(CleanupIncomplete) as excinfo:
            run_cleanup(settings, http)

    # Every store that refused is named, so the failure says what survived
    # rather than that something did.
    message = str(excinfo.value)
    for db_name in (*DATABASES, *EDC_DATABASES):
        assert db_name in message


# ── The harness does not reach an EDC management API ────────────────────────


def test_the_harness_has_no_edc_management_setting_or_key():
    """The management port is not published and there is no shared key (plan
    `the-management-api-is-v3-behind-one-key`, decision 1). A setting that
    names either invites a flow to use it."""
    fields = set(E2ESettings.model_fields)
    assert "edc_api_key" not in fields
    assert not [f for f in fields if "management_url" in f]


def test_cleanup_issues_no_http_call_at_all():
    """Not one — not to an EDC, and since 2026-09-18 not to a connector either.

    The re-sync that used to live here ran *before* `e2e:prepare` restarts the
    EDCs, i.e. against a database whose schema had just been dropped. It is
    `task e2e:sync-providers` that publishes, after the restart and the
    readiness gate. `provider_sync_targets` stays: the Taskfile's own re-sync
    (`ds-e2e resync-providers`) enumerates the providers through it.
    """
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    with patch("ds_e2e.cleanup.psycopg.connect"):
        run_cleanup(settings, http)
    assert http.post.call_count == 0
    assert http.get.call_count == 0
    # The list itself is still the one place the providers are enumerated.
    assert [label for _, label in provider_sync_targets(settings)] == [
        "provider",
        "grid-operator",
    ]


def test_the_keycloak_token_url_is_too():
    """It was the one default in `config.py` on `localhost` (`E2E-07`), so the
    harness authenticated from a laptop and not from a container — and the
    failure read as "Keycloak is down"."""
    settings = E2ESettings(_env_file=None)
    assert "172.17.0.1" in settings.keycloak_token_url
    assert "localhost" not in settings.keycloak_token_url


def test_a_clean_that_could_not_finish_raises():
    """`Cleanup complete` must not be printed over work that did not happen.

    The failures were logged and swallowed, so `run_cleanup` returned normally
    and the next run started on the previous run's agreements — surfacing as an
    unrelated flow failing on stale state, with nothing connecting it back.
    """
    import psycopg

    settings = E2ESettings(_env_file=None)
    http = MagicMock()

    with patch(
        "ds_e2e.cleanup.psycopg.connect",
        side_effect=psycopg.Error("connection refused"),
    ):
        with pytest.raises(CleanupIncomplete) as exc:
            run_cleanup(settings, http)

    # Every store named, not just the first one to fail.
    for db_name in (*DATABASES, *EDC_DATABASES):
        assert db_name in str(exc.value)


def test_a_clean_that_finished_returns_quietly():
    settings = E2ESettings(_env_file=None)
    http = MagicMock()
    http.bearer_headers.return_value = {}
    with patch("ds_e2e.cleanup.psycopg.connect"):
        run_cleanup(settings, http)
