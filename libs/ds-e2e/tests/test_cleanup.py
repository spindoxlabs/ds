"""Tests for cleanup module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ds_e2e.cleanup import (
    DATABASES,
    EDC_DATABASES,
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

    with patch("ds_e2e.cleanup.psycopg.connect", return_value=mock_conn) as mock_connect:
        run_cleanup(settings, http)

    # One connection per application database it truncates, plus one to the
    # `postgres` database per EDC store it drops and recreates.
    assert mock_connect.call_count == len(DATABASES) + len(EDC_DATABASES)
    # One TRUNCATE per application database; a DROP and a CREATE per EDC store.
    assert mock_cursor.execute.call_count == len(DATABASES) + 2 * len(EDC_DATABASES)
    # Every provider re-syncs, and the assertion names *which* — a count alone
    # went stale the moment `DID-15` added the second one.
    assert [c.args[0] for c in http.post.call_args_list] == [
        f"{url}/provider/sync" for url, _ in provider_sync_targets(settings)
    ]


def test_cleanup_continues_on_db_error():
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {"Authorization": "Bearer tok"}
    http.post.return_value = {}

    import psycopg
    with patch("ds_e2e.cleanup.psycopg.connect", side_effect=psycopg.Error("connection refused")):
        run_cleanup(settings, http)

    # A database that refused every connection must not stop the provider syncs:
    # the point of the clean is that the *next* run starts from a known state.
    assert [c.args[0] for c in http.post.call_args_list] == [
        f"{url}/provider/sync" for url, _ in provider_sync_targets(settings)
    ]
