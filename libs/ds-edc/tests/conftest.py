"""A fake EDC control plane.

`httpx.MockTransport` rather than `respx`, because these tests care about what
this client does with a *status code and body* it did not expect, and the plain
transport makes each case one line.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from ds_edc.client import EdcManagementClient

BASE = "http://edc.test/management"
CONTEXT_ID = "did:web:rec.example.org"
#: The path every resource call is under, as EDC 0.18.0 serves it.
ROOT = "/management/v5beta/participants/did%3Aweb%3Arec.example.org"


class RecordingEdc:
    """Answers whatever the test says, and remembers what it was asked."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]):
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


@pytest.fixture
def edc_client():
    """Build a client whose transport the test controls.

    The client owns its `AsyncClient`, so the transport is swapped in after
    construction; the bearer auth is carried over, which keeps it under test in
    `test_v5.py`.
    """

    def _build(handler: Callable[[httpx.Request], httpx.Response]):
        fake = RecordingEdc(handler)

        async def token() -> str:
            return "org-token"

        client = EdcManagementClient(BASE, CONTEXT_ID, token_source=token)
        client._http = httpx.AsyncClient(
            base_url=BASE,
            auth=client._http.auth,
            transport=httpx.MockTransport(fake),
        )
        return client, fake

    return _build


def json_response(status: int, payload):
    return httpx.Response(status, json=payload)


def status_only(status: int, text: str = ""):
    return httpx.Response(status, text=text)
