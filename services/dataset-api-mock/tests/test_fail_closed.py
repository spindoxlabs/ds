"""What this PEP does when a dependency will not answer.

`_authorize` was already fail-closed and says so in a comment. The paths around
it were not, and they failed in three different ways:

* `_verification_keys` let `raise_for_status` and `RequestError` escape as a
  **500**;
* `_internal_headers` let the Keycloak token fetch escape the same way — inside
  `_audit_query`, that is a 500 raised *after* the decision was taken;
* `_audit_query` ignored a non-2xx entirely and swallowed a `RequestError`, so
  the same failure served rows or refused them depending on its shape.

A 500 and a 502 both refuse the request, so none of this is a leak on its own.
It matters because the failure mode is what an operator reads to decide which
component is broken, and because "sometimes fatal" is not a policy.
"""

from __future__ import annotations

import httpx
import pytest
from ds.governance import ALLOW, DataplaneDecision
from fastapi import HTTPException
from fastapi.testclient import TestClient

from dataset_api_mock import main
from dataset_api_mock.main import REC_REGISTRY

GATED = "datasets.silver.meters_15m"
SUBJECT = "subject@example.test"

HEADERS = {
    "Authorization": "Bearer irrelevant-the-verifier-is-stubbed",
    "Edc-Contract-Agreement-Id": "agr-1",
    "Edc-Purpose": "FlexibilityResearch",
}


def _allowing_decision() -> DataplaneDecision:
    return DataplaneDecision.model_validate({
        "decision": ALLOW,
        "agreement_id": "agr-1",
        "purpose": ["FlexibilityResearch"],
        "datasets": [{
            "dataset_id": GATED,
            "decision": ALLOW,
            "row_filter": {
                "handler": REC_REGISTRY,
                "args": {"column": "device_id"},
                "principals": [SUBJECT],
            },
        }],
    })


@pytest.fixture
def client(monkeypatch):
    async def consumer(_bearer):
        return "did:web:third-party.dataspaces.localhost"

    async def authorize(**_kwargs):
        return _allowing_decision()

    monkeypatch.setattr(main, "_verified_consumer", consumer)
    monkeypatch.setattr(main, "_authorize", authorize)
    return TestClient(main.app)


def _query(client):
    return client.post(
        "/query", json={"sql": f"SELECT * FROM {GATED}", "limit": 100}, headers=HEADERS
    )


def _request_error(*_args, **_kwargs):
    raise httpx.ConnectError("connection refused")


def _status_error(status: int):
    def raise_it(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ds/internal")
        raise httpx.HTTPStatusError(
            "refused", request=request, response=httpx.Response(status, request=request)
        )

    return raise_it


# ── Keycloak ──────────────────────────────────────────────────────────────────


async def test_an_unreachable_keycloak_is_a_502(monkeypatch):
    """Not a 500. A PEP that cannot prove who it is has not been told it may
    serve anything, and the distinction it needs to report is *which* dependency
    would not answer."""
    monkeypatch.setattr(main, "_token_provider", _request_error)
    with pytest.raises(HTTPException) as exc:
        await main._internal_headers()
    assert exc.value.status_code == 502
    assert "Keycloak" in exc.value.detail


async def test_keycloak_refusing_the_token_is_a_502(monkeypatch):
    """A wrong client secret is a 401 from Keycloak, and used to surface as a 500
    from a service that was working exactly as configured."""
    monkeypatch.setattr(main, "_token_provider", _status_error(401))
    with pytest.raises(HTTPException) as exc:
        await main._internal_headers()
    assert exc.value.status_code == 502
    assert "401" in exc.value.detail


# ── The EDR key set ───────────────────────────────────────────────────────────


async def test_an_unreachable_connector_is_a_502_on_the_key_fetch(monkeypatch):
    async def headers():
        return {}

    monkeypatch.setattr(main, "_internal_headers", headers)
    main._jwks_cache.pop("keys", None)
    monkeypatch.setattr(httpx.AsyncClient, "get", _request_error)

    with pytest.raises(HTTPException) as exc:
        await main._verification_keys()
    assert exc.value.status_code == 502


async def test_the_connector_refusing_the_key_set_is_a_502(monkeypatch):
    """`raise_for_status` used to escape uncaught."""
    async def headers():
        return {}

    async def get(*_args, **_kwargs):
        request = httpx.Request("GET", "http://ds/internal/edr-jwks")
        return httpx.Response(403, request=request)

    monkeypatch.setattr(main, "_internal_headers", headers)
    main._jwks_cache.pop("keys", None)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)

    with pytest.raises(HTTPException) as exc:
        await main._verification_keys()
    assert exc.value.status_code == 502
    assert "403" in exc.value.detail


async def test_a_token_that_fits_no_key_drops_the_cached_set(monkeypatch):
    """`_verification_keys` documents this and nothing did it.

    The commonest cause of no key fitting is a provider rotation, and a cache
    that is never invalidated turns that into a restart rather than a retry.
    """
    main._jwks_cache["keys"] = ["a stale key"]

    async def keys():
        return ["a stale key"]

    monkeypatch.setattr(main, "_verification_keys", keys)
    with pytest.raises(HTTPException) as exc:
        await main._verified_consumer("Bearer not.a.valid.token")
    assert exc.value.status_code == 401
    assert "keys" not in main._jwks_cache


# ── The audit event ───────────────────────────────────────────────────────────


def test_an_unrecordable_query_serves_no_rows(client, monkeypatch):
    """Rulebook `L-1`: recording is not optional.

    This is available *because of where the audit call sits* — the rows are read
    and narrowed but not yet returned, so a request that fails here discloses
    nothing and therefore needs no record. Serving them would leave a disclosure
    with no `QueryExecuted` event.
    """
    monkeypatch.setattr(httpx.AsyncClient, "post", _request_error)
    response = _query(client)
    assert response.status_code == 502
    assert "items" not in response.json()


def test_an_audit_the_connector_refuses_serves_no_rows(client, monkeypatch):
    """A non-2xx was ignored completely: no `raise_for_status`, no log, no effect.

    So the one failure that means "ds rejected this record" was the one failure
    that changed nothing.
    """
    async def post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ds/internal/audit/query")
        return httpx.Response(422, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert _query(client).status_code == 502


def test_the_audit_failure_policy_does_not_depend_on_how_it_failed(client, monkeypatch):
    """Three shapes of failure, one outcome.

    It used to be three: a non-2xx served the rows, a `RequestError` served the
    rows, and an `HTTPStatusError` out of the token fetch raised a 500.
    """
    outcomes = set()

    async def unreachable(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    async def rejected(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ds/internal/audit/query")
        return httpx.Response(500, request=request)

    for failure in (unreachable, rejected):
        monkeypatch.setattr(httpx.AsyncClient, "post", failure)
        outcomes.add(_query(client).status_code)

    monkeypatch.setattr(main, "_token_provider", _status_error(401))
    outcomes.add(_query(client).status_code)

    assert outcomes == {502}


# ── The external upstream ─────────────────────────────────────────────────────


async def test_an_external_query_carries_a_credential(monkeypatch):
    """It went out bare.

    Which means either the upstream accepts anonymous queries — so anyone who can
    reach it holds the same access this service does — or the call never worked
    and the dataset was unserveable. The second hides the first.
    """
    seen: dict = {}

    async def headers():
        return {"Authorization": "Bearer svc-token"}

    async def post(_self, url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers")
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"items": []}, request=request)

    monkeypatch.setattr(main.settings, "external_query_url", "http://upstream:8000")
    monkeypatch.setattr(main, "_internal_headers", headers)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    await main._query_external({"external_sql": "SELECT 1", "requires_consent": False})
    assert seen["headers"]["Authorization"] == "Bearer svc-token"
