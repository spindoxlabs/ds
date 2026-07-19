from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from ds_e2e.config import E2ESettings

log = logging.getLogger(__name__)


class HttpError(Exception):
    def __init__(self, status: int, body: Any, url: str):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} from {url}")


class HttpClient:
    def __init__(self, settings: E2ESettings):
        self._settings = settings
        self._client = httpx.Client(timeout=settings.request_timeout)
        self._token: str | None = None
        self._token_expires: float = 0.0

    def close(self) -> None:
        self._client.close()

    def get(
        self, url: str, *, headers: dict[str, str] | None = None, raise_for_status: bool = True
    ) -> Any:
        return self._request("GET", url, headers=headers, raise_for_status=raise_for_status)

    def post(
        self,
        url: str,
        body: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        raise_for_status: bool = True,
    ) -> Any:
        return self._request("POST", url, body=body, headers=headers, raise_for_status=raise_for_status)

    def get_raw(self, url: str, *, headers: dict[str, str] | None = None) -> tuple[int, Any]:
        return self._request_raw("GET", url, headers=headers)

    def post_raw(
        self, url: str, body: dict[str, Any] | None = None, *, headers: dict[str, str] | None = None
    ) -> tuple[int, Any]:
        return self._request_raw("POST", url, body=body, headers=headers)

    def poll_until(
        self,
        url: str,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        timeout: int | None = None,
        interval: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        timeout = timeout or self._settings.poll_timeout
        interval = interval or self._settings.poll_interval
        deadline = time.time() + timeout
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self.get(url, headers=headers, raise_for_status=False) or {}
            if isinstance(last, dict) and predicate(last):
                return last
            time.sleep(interval)
        return last

    def acquire_service_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires:
            return self._token

        resp = self._client.post(
            self._settings.keycloak_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.service_client_id,
                "client_secret": self._settings.service_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = now + data.get("expires_in", 300) - 30
        log.debug("Acquired service token (expires in %ds)", data.get("expires_in", 300))
        return self._token

    def bearer_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.acquire_service_token()}"}

    def _request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        raise_for_status: bool = True,
    ) -> Any:
        log.debug("%s %s", method, url)
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        if headers:
            kwargs["headers"] = headers

        resp = self._client.request(method, url, **kwargs)

        if raise_for_status and resp.status_code >= 400:
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text
            raise HttpError(resp.status_code, payload, url)

        if not resp.text:
            return None
        try:
            return resp.json()
        except Exception:
            return resp.text

    def _request_raw(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        log.debug("%s %s (raw)", method, url)
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        if headers:
            kwargs["headers"] = headers

        resp = self._client.request(method, url, **kwargs)
        if not resp.text:
            return resp.status_code, None
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text
