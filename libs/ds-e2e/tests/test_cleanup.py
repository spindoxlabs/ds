"""Tests for cleanup module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ds_e2e.cleanup import DATABASES, run_cleanup
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

    assert mock_connect.call_count == len(DATABASES)
    assert mock_cursor.execute.call_count == len(DATABASES)
    http.post.assert_called_once()


def test_cleanup_continues_on_db_error():
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {"Authorization": "Bearer tok"}
    http.post.return_value = {}

    import psycopg
    with patch("ds_e2e.cleanup.psycopg.connect", side_effect=psycopg.Error("connection refused")):
        run_cleanup(settings, http)

    http.post.assert_called_once()
