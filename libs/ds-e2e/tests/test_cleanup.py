"""Tests for cleanup module.

**These tests used to clean the developer's running stack** (`E2E-17`).
`run_cleanup` built its own `httpx.Client`, so mocking `psycopg` and
`HttpClient` left the EDC Management API calls live: eight green assertions
here deleted every contract definition and policy from both providers' EDCs.
The client is now injected, and `conftest.py` refuses any socket in this suite
so the next such path fails loudly instead of succeeding quietly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from ds_e2e.cleanup import (
    DATABASES,
    EDC_DATABASES,
    provider_sync_targets,
    run_cleanup,
)
from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient


def fake_edc_client(items=()):
    """An `httpx.Client` stand-in that reaches nothing.

    `_edc_list` reads `.json()`, so the GET answer is shaped like a Management
    API list response; everything else only has to not raise."""
    client = MagicMock(spec=httpx.Client)
    response = MagicMock()
    response.json.return_value = list(items)
    response.status_code = 200
    client.get.return_value = response
    client.post.return_value = response
    client.delete.return_value = response
    return client


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

    edc = fake_edc_client()
    with patch(
        "ds_e2e.cleanup.psycopg.connect", return_value=mock_conn
    ) as mock_connect:
        run_cleanup(settings, http, edc_client=edc)

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

    with patch(
        "ds_e2e.cleanup.psycopg.connect",
        side_effect=psycopg.Error("connection refused"),
    ):
        run_cleanup(settings, http, edc_client=fake_edc_client())

    # A database that refused every connection must not stop the provider syncs:
    # the point of the clean is that the *next* run starts from a known state.
    assert [c.args[0] for c in http.post.call_args_list] == [
        f"{url}/provider/sync" for url, _ in provider_sync_targets(settings)
    ]


# ── E2E-07 · the EDC control plane is configuration, not a constant ──────────


def test_the_edc_key_and_urls_come_from_settings():
    """Module constants until now, so a stack whose EDC key or ports differed
    could not be cleaned — and the clean said it had succeeded, because a 401 on
    a delete was never checked."""
    from ds_e2e.cleanup import edc_headers, edc_management_urls

    settings = E2ESettings(_env_file=None)
    assert edc_headers(settings)["x-api-key"] == settings.edc_api_key
    assert set(edc_management_urls(settings)) == {
        "provider",
        "consumer",
        "grid-operator",
    }


def test_overriding_the_edc_key_reaches_the_headers(monkeypatch):
    monkeypatch.setenv("EDC_API_KEY", "a-real-generated-key")
    from ds_e2e.cleanup import edc_headers

    assert (
        edc_headers(E2ESettings(_env_file=None))["x-api-key"] == "a-real-generated-key"
    )


def test_every_management_url_is_on_the_host_gateway():
    """The host-binding rule: `172.17.0.1` resolves identically from the host and
    from a container, which is what makes the local and Docker layers
    interchangeable. `localhost` does not."""
    from ds_e2e.cleanup import edc_management_urls

    for role, url in edc_management_urls(E2ESettings(_env_file=None)).items():
        assert "172.17.0.1" in url, f"{role} is not on the host gateway: {url}"


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

    Found live: threading settings through the EDC calls left one call site
    unfixed, all 60 unit tests stayed green, and the clean printed three
    warnings and then `Cleanup complete`.
    """
    import pytest

    from ds_e2e.cleanup import CleanupIncomplete

    settings = E2ESettings(_env_file=None)
    http = MagicMock()
    http.bearer_headers.return_value = {}

    with (
        patch("ds_e2e.cleanup.psycopg.connect"),
        patch(
            "ds_e2e.cleanup._clear_edc",
            side_effect=RuntimeError("control plane refused"),
        ),
    ):
        with pytest.raises(CleanupIncomplete) as exc:
            run_cleanup(settings, http)

    # Every control plane named, not just the first one to fail — an operator
    # fixing one at a time re-runs three times otherwise.
    for role in ("provider", "consumer", "grid-operator"):
        assert role in str(exc.value)


def test_a_clean_that_finished_returns_quietly():
    settings = E2ESettings(_env_file=None)
    http = MagicMock()
    http.bearer_headers.return_value = {}
    with patch("ds_e2e.cleanup.psycopg.connect"), patch("ds_e2e.cleanup._clear_edc"):
        run_cleanup(settings, http)


# ── E2E-17 · the clean must only clean what it was handed ────────────────────


def test_the_clean_sends_its_deletes_to_the_injected_client(monkeypatch):
    """The regression guard for `E2E-17`, stated as the property it broke.

    `run_cleanup` must issue **every** EDC call through the client it was
    given. It did not: it constructed one, so a caller that had mocked
    everything it knew about still reached three live control planes. The
    assertion is on the fake receiving the deletes — if a future edit builds a
    client again, the fake sees nothing and this fails.
    """
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {}
    edc = fake_edc_client(items=[{"@id": "some-contract-definition"}])

    with patch("ds_e2e.cleanup.psycopg.connect"):
        run_cleanup(settings, http, edc_client=edc)

    deleted = [c.args[0] for c in edc.delete.call_args_list]
    assert deleted, "the clean issued no deletes through the injected client"
    # Three control planes × three resource kinds, all through the fake.
    for role_url in ("19193", "29193", "39193"):
        assert any(role_url in url for url in deleted)


def test_the_clean_does_not_close_a_client_it_was_given():
    """The caller owns the lifetime of a client it passed in.

    Closing it here would break the caller's next use of it, and the failure
    would appear far from this function."""
    settings = E2ESettings(_env_file=None)
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {}
    edc = fake_edc_client()

    with patch("ds_e2e.cleanup.psycopg.connect"):
        run_cleanup(settings, http, edc_client=edc)

    edc.close.assert_not_called()
