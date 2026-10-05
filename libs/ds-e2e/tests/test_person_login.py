"""R3: a flow presents a person's own login, fetched when the request is sent.

Person routes take the person's Keycloak token beside their credential. The dev
realm's tokens live five minutes, shorter than the longest flows, so a flow holds
a marker naming the person and the client swaps it for a current token per
request (`http.PERSON_LOGIN_HEADER`).
"""

from __future__ import annotations

import httpx

from ds_e2e.config import E2ESettings
from ds_e2e.http import PERSON_LOGIN_HEADER, HttpClient


def _client(handler) -> HttpClient:
    client = HttpClient(E2ESettings(_env_file=None))
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_the_marker_becomes_the_persons_current_token():
    seen: list[dict] = []
    grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/protocol/openid-connect/token"):
            form = dict(httpx.QueryParams(request.content.decode()))
            grants.append(form["grant_type"] + ":" + form["username"])
            return httpx.Response(
                200, json={"access_token": "person-token", "expires_in": 300}
            )
        seen.append(dict(request.headers))
        return httpx.Response(200, json={})

    client = _client(handler)
    headers = {
        "X-Subject-Id": "did:web:x:users:s",
        "X-User-VC": "vc",
        **client.person_login("subject@example.test", "subject"),
    }
    assert headers[PERSON_LOGIN_HEADER] == "subject@example.test"
    assert "Authorization" not in headers, "the flow never holds the token"

    client.get("http://connector.test/consent/my", headers=headers)
    client.raw("GET", "http://connector.test/consent/my", headers=headers)

    assert grants == ["password:subject@example.test"], "fetched once, then reused"
    for request_headers in seen:
        assert request_headers["authorization"] == "Bearer person-token"
        assert PERSON_LOGIN_HEADER.lower() not in request_headers
        assert request_headers["x-user-vc"] == "vc"


def test_headers_without_the_marker_are_sent_as_given():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(200, json={})

    client = _client(handler)
    client.get("http://connector.test/x", headers={"Authorization": "Bearer svc"})
    assert seen[0]["authorization"] == "Bearer svc"
