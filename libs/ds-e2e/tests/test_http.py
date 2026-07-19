"""Tests for HttpClient (unit tests with mocked responses)."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient, HttpError


@pytest.fixture
def settings():
    return E2ESettings(_env_file=None)


@pytest.fixture
def client(settings):
    c = HttpClient(settings)
    yield c
    c.close()


def _mock_response(status: int = 200, json_data: dict | list | None = None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = json.dumps(json_data) if json_data is not None else text
    resp.json.return_value = json_data
    return resp


def test_get_success(client):
    mock_resp = _mock_response(200, {"status": "ok"})
    with patch.object(client._client, "request", return_value=mock_resp):
        result = client.get("http://example.com/health")
    assert result == {"status": "ok"}


def test_get_raises_on_4xx(client):
    mock_resp = _mock_response(403, {"detail": "forbidden"})
    with patch.object(client._client, "request", return_value=mock_resp):
        with pytest.raises(HttpError) as exc_info:
            client.get("http://example.com/secret")
    assert exc_info.value.status == 403


def test_get_raw_returns_status_and_body(client):
    mock_resp = _mock_response(404, {"detail": "not found"})
    with patch.object(client._client, "request", return_value=mock_resp):
        status, body = client.get_raw("http://example.com/missing")
    assert status == 404
    assert body == {"detail": "not found"}


def test_post_sends_json(client):
    mock_resp = _mock_response(200, {"id": "123"})
    with patch.object(client._client, "request", return_value=mock_resp) as mock_req:
        result = client.post("http://example.com/create", {"name": "test"})
    assert result == {"id": "123"}
    call_kwargs = mock_req.call_args[1]
    assert call_kwargs["json"] == {"name": "test"}


def test_poll_until_succeeds(client):
    responses = [
        _mock_response(200, {"state": "PENDING"}),
        _mock_response(200, {"state": "PENDING"}),
        _mock_response(200, {"state": "DONE"}),
    ]
    with patch.object(client._client, "request", side_effect=responses):
        with patch("ds_e2e.http.time.sleep"):
            result = client.poll_until(
                "http://example.com/status",
                lambda p: p.get("state") == "DONE",
                timeout=10,
                interval=0.01,
            )
    assert result == {"state": "DONE"}


def test_poll_until_timeout(client):
    mock_resp = _mock_response(200, {"state": "PENDING"})
    with patch.object(client._client, "request", return_value=mock_resp):
        with patch("ds_e2e.http.time.time", side_effect=[0, 0, 0.5, 1.1]):
            with patch("ds_e2e.http.time.sleep"):
                result = client.poll_until(
                    "http://example.com/status",
                    lambda p: p.get("state") == "DONE",
                    timeout=1,
                    interval=0.01,
                )
    assert result == {"state": "PENDING"}


def test_acquire_service_token(client):
    token_resp = _mock_response(200, {"access_token": "tok123", "expires_in": 300})
    with patch.object(client._client, "post", return_value=token_resp) as mock_post:
        token_resp.raise_for_status = MagicMock()
        token = client.acquire_service_token()
    assert token == "tok123"
    assert client.bearer_headers() == {"Authorization": "Bearer tok123"}


def test_service_token_cached(client):
    token_resp = _mock_response(200, {"access_token": "tok123", "expires_in": 300})
    token_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "post", return_value=token_resp) as mock_post:
        client.acquire_service_token()
        client.acquire_service_token()
    assert mock_post.call_count == 1
