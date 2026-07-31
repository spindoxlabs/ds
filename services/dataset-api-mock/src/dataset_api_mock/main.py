from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import jwt
from ds.governance import (
    DIRECT_USER_MATCH,
    DataplaneDecision,
    DataplaneRowFilter,
)
from ds_auth.production import ProductionGuard
from ds_auth.service_token import ServiceTokenProvider
from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from .metrics import install_metrics

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATASET_API_", extra="ignore")

    connector_internal_url: str = "http://172.17.0.1:30001"
    # This service's own identity on ds-connector's /internal/* API.
    # `svc-ds-dataset-api` holds `connector.internal` with `svc-ds-connector` in
    # its audience. This replaced `connector_api_key`, which was the same value
    # as EDC's Management API key — one secret across two trust boundaries.
    keycloak_token_url: str = (
        "http://172.17.0.1:9080/realms/dataspaces/protocol/openid-connect/token"
    )
    service_client_id: str = "svc-ds-dataset-api"
    service_client_secret: str = "svc-ds-dataset-api"
    enforce_consent: bool = True
    external_query_url: str | None = None
    extra_datasets_path: str | None = None
    # Verify the EDR token's signature against ds's JWKS proxy. Off only for a
    # stack whose EDC JWKS is unreachable; `_check_production_config` refuses it
    # in production, because with it off a bearer string is an assertion.
    verify_edr: bool = True


settings = Settings()
app = FastAPI(title="dataset-api-mock", version="0.1.0")
install_metrics(app, "dataset-api")

_token_provider = ServiceTokenProvider(
    token_url=settings.keycloak_token_url,
    client_id=settings.service_client_id,
    client_secret=settings.service_client_secret,
)


def _check_production_config() -> None:
    """Refuse to run with the dev client secret when ``DS_ENV=production``.

    A weak secret still authenticates, so nothing about a running system would
    look wrong. Registering it here is what makes the omission loud.
    """
    guard = ProductionGuard("dataset-api")
    guard.forbid_default(
        "DATASET_API_SERVICE_CLIENT_SECRET",
        settings.service_client_secret,
        {"svc-ds-dataset-api"},
        "Set the Keycloak client secret for svc-ds-dataset-api.",
    )
    if not settings.verify_edr:
        guard.forbid_default(
            "DATASET_API_VERIFY_EDR",
            "false",
            {"false"},
            "Nothing else validates the EDR token in this topology — with "
            "verification off, any bearer string names any consumer.",
        )
    guard.enforce()


_check_production_config()


DATASETS: dict[str, dict[str, Any]] = {
    "datasets.gold.om_weather_features": {
        "asset_id": "datasets.gold.om_weather_features",
        "requires_consent": False,
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "location": "EC-001", "temperature_c": 18.7, "wind_ms": 2.8, "ghi": 426},
            {"timestamp": "2026-05-11T08:15:00Z", "location": "EC-001", "temperature_c": 18.9, "wind_ms": 2.6, "ghi": 441},
            {"timestamp": "2026-05-11T08:30:00Z", "location": "EC-001", "temperature_c": 19.1, "wind_ms": 2.5, "ghi": 455},
        ],
    },
    "datasets.silver.meters_15m": {
        "asset_id": "datasets.silver.meters_15m",
        "requires_consent": True,
        "subject_column": "sub",
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "sub": "did:web:users.dataspaces.localhost:data-subject", "meter_id": "MTR-001", "kwh": 0.42},
            {"timestamp": "2026-05-11T08:15:00Z", "sub": "did:web:users.dataspaces.localhost:data-subject", "meter_id": "MTR-001", "kwh": 0.37},
            {"timestamp": "2026-05-11T08:00:00Z", "sub": "did:web:users.dataspaces.localhost:subject-002", "meter_id": "MTR-002", "kwh": 0.55},
            {"timestamp": "2026-05-11T08:15:00Z", "sub": "did:web:users.dataspaces.localhost:subject-002", "meter_id": "MTR-002", "kwh": 0.51},
        ],
    },
}


def _load_extra_datasets(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise RuntimeError(f"Extra dataset file not found: {dataset_path}")
    payload = json.loads(dataset_path.read_text())
    datasets = payload.get("datasets", payload)
    if not isinstance(datasets, dict):
        raise RuntimeError("Extra dataset file must contain a dataset object")
    return datasets


DATASETS.update(_load_extra_datasets(settings.extra_datasets_path))


def _catalogue_entry(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    medallion = "gold" if ".gold." in name else "silver" if ".silver." in name else "bronze"
    access_level = "restricted" if spec["requires_consent"] else "internal"
    keywords = [medallion]
    if spec["requires_consent"]:
        keywords.extend(["pii", "consent"])

    return {
        "@id": spec["asset_id"],
        "id": spec["asset_id"],
        "name": name,
        "asset_id": spec["asset_id"],
        "dct:title": name.replace("_", " ").replace(".", " / "),
        "title": name,
        "dct:description": (
            "Consent-protected smart meter sample rows."
            if spec["requires_consent"]
            else "Open weather feature sample rows."
        ),
        "description": (
            "Consent-protected smart meter sample rows."
            if spec["requires_consent"]
            else "Open weather feature sample rows."
        ),
        "dcat:keyword": keywords,
        "access_level": access_level,
        "requires_consent": spec["requires_consent"],
        "rows": len(spec["rows"]),
        "odrl:hasPolicy": {
            "@type": "odrl:Offer",
            "odrl:permission": [
                {
                    "odrl:action": "use",
                    "odrl:constraint": [
                        {
                            "odrl:leftOperand": "ds:consentStatus",
                            "odrl:operator": "odrl:eq",
                            "odrl:rightOperand": "granted",
                        }
                    ]
                    if spec["requires_consent"]
                    else [],
                }
            ],
        },
    }


def _dataset_enabled(spec: dict[str, Any]) -> bool:
    return spec.get("source") != "external" or bool(settings.external_query_url)


def _enabled_datasets() -> dict[str, dict[str, Any]]:
    return {name: spec for name, spec in DATASETS.items() if _dataset_enabled(spec)}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/datasets")
async def datasets() -> dict[str, list[dict[str, Any]]]:
    return {
        "datasets": [
            {
                "name": name,
                "asset_id": spec["asset_id"],
                "requires_consent": spec["requires_consent"],
                "rows": len(spec["rows"]),
            }
            for name, spec in _enabled_datasets().items()
        ]
    }


@app.get("/subjects/{subject_id}/datasets")
async def subject_datasets(subject_id: str) -> dict[str, Any]:
    """Return datasets containing data owned by a data subject.

    This endpoint is the data adapter's inventory view. It does not grant
    access; sharing is still enforced by ds-connector consent checks.
    """
    owned: list[dict[str, Any]] = []
    for name, spec in _enabled_datasets().items():
        subject_column = spec.get("subject_column")
        if not subject_column:
            continue

        sample_rows = list(spec.get("rows") or [])
        subject_match = spec.get("subject_id") == subject_id or any(
            row.get(subject_column) == subject_id for row in sample_rows
        )
        if not subject_match:
            continue

        owned.append({
            "name": name,
            "asset_id": spec["asset_id"],
            "title": name.replace("_", " ").replace(".", " / "),
            "requires_consent": spec["requires_consent"],
            "subject_column": subject_column,
            "sample_rows": sum(1 for row in sample_rows if row.get(subject_column) == subject_id),
            "source": spec.get("source", "local"),
        })
    return {"subject_id": subject_id, "datasets": owned}


@app.get("/catalogue")
async def catalogue() -> dict[str, list[dict[str, Any]]]:
    return {"datasets": [_catalogue_entry(name, spec) for name, spec in _enabled_datasets().items()]}


@app.get("/catalogue/{asset_id:path}")
async def catalogue_item(asset_id: str) -> dict[str, Any]:
    for name, spec in _enabled_datasets().items():
        if asset_id in {name, spec["asset_id"]}:
            return _catalogue_entry(name, spec)
    raise HTTPException(404, f"Unknown asset {asset_id!r}")


class DatasetQueryModel(BaseModel):
    """Mirrors `celine.dataset.schemas.dataset_query.DatasetQueryModel`.

    Field for field, including the defaults. A mock whose request model differs
    from the real one validates a contract nobody runs.
    """

    sql: str | None = None
    limit: int = 100
    offset: int = 0
    skip_count: bool = False


class DatasetQueryResult(BaseModel):
    """Mirrors `celine.dataset.schemas.dataset_query.DatasetQueryResult`."""

    items: list[dict[str, Any]]
    offset: int
    limit: int
    count: int
    total: int | None = None


@app.post("/query", response_model=DatasetQueryResult)
async def query(
    body: DatasetQueryModel,
    authorization: str | None = Header(default=None),
    edc_contract_agreement_id: str | None = Header(default=None),
    edc_transfer_process_id: str | None = Header(default=None),
    edc_purpose: str | None = Header(default=None),
) -> DatasetQueryResult:
    """Query datasets — in dataspace mode, or the way this service always worked.

    **`Edc-Contract-Agreement-Id` present → dataspace mode.** Absent → the plain
    path, which is what a non-dataspace deployment runs today and which this
    change must not disturb.

    Dataspace mode never falls back to the plain path on failure. A fallback
    between two authorization regimes is a bypass with extra steps.

    The datasets come from the query itself, never from a parameter: what a
    caller may read is decided by ds from the agreement, and letting the caller
    *name* the dataset alongside it invites the two to disagree.
    """
    dataset_names = _datasets_in_sql(body.sql)
    if not dataset_names:
        raise HTTPException(400, "No known dataset referenced in the query")

    if edc_contract_agreement_id is None:
        return await _plain_query(dataset_names, body)

    return await _dataspace_query(
        dataset_names,
        body,
        bearer=authorization,
        agreement_id=edc_contract_agreement_id,
        transfer_id=edc_transfer_process_id,
        purpose=edc_purpose,
    )


def _datasets_in_sql(sql: str | None) -> list[str]:
    """Which known datasets does this statement touch?

    The real service resolves them through the catalogue and its SQL parser;
    the FIWARE/QuantumLeap module resolves them its own way. Matching known
    names against the statement is the mock's equivalent — the *contract* is
    "the query says which datasets", and that is what has to be identical.
    """
    if not sql:
        return []
    return [name for name in _enabled_datasets() if name in sql]


async def _rows_for(dataset_names: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    name = dataset_names[0]
    spec = DATASETS[name]
    rows = (
        await _query_external(spec)
        if spec.get("source") == "external"
        else list(spec["rows"])
    )
    return rows, spec


def _page(rows: list[dict[str, Any]], body: DatasetQueryModel) -> DatasetQueryResult:
    window = rows[body.offset : body.offset + body.limit]
    return DatasetQueryResult(
        items=window,
        offset=body.offset,
        limit=body.limit,
        count=len(window),
        total=None if body.skip_count else len(rows),
    )


async def _plain_query(dataset_names: list[str], body: DatasetQueryModel) -> DatasetQueryResult:
    """Non-dataspace mode: no ds involvement at all, by design."""
    rows, _ = await _rows_for(dataset_names)
    return _page(rows, body)


async def _dataspace_query(
    dataset_names: list[str],
    body: DatasetQueryModel,
    *,
    bearer: str | None,
    agreement_id: str,
    transfer_id: str | None,
    purpose: str | None,
) -> DatasetQueryResult:
    consumer_did = await _verified_consumer(bearer)

    decision = await _authorize(
        consumer_did=consumer_did,
        agreement_id=agreement_id,
        transfer_id=transfer_id,
        purpose=[p.strip() for p in (purpose or "").split(",") if p.strip()],
        dataset_ids=[DATASETS[n]["asset_id"] for n in dataset_names],
    )
    if not decision.allowed:
        # The reason is ds's, and it is safe to relay: it names the gate, never
        # who else holds the agreement.
        raise HTTPException(403, f"Refused by ds: {decision.reason}")

    rows, spec = await _rows_for(dataset_names)
    verdict = decision.verdict_for(spec["asset_id"])
    if verdict is None or not verdict.allowed:
        # The envelope allowed, this dataset did not — or ds never mentioned it.
        # Either way nothing here has been permitted to serve it.
        raise HTTPException(
            403, f"Refused by ds: {verdict.reason if verdict else 'dataset_undecided'}"
        )

    if verdict.row_filter is not None:
        rows = _apply_row_filter(rows, verdict.row_filter)

    await _audit_query(
        dataset_id=spec["asset_id"],
        consumer_id=consumer_did,
        subject_id=None,
        agreement_id=agreement_id,
        transfer_id=transfer_id,
        row_count=len(rows),
        # **Deliberately not the filter's principals.** `/internal/audit/query`
        # declares `authorized_subject_ids`, and a PEP structurally cannot fill
        # it: ds translates subject DIDs into registry-native principals before
        # the filter leaves, precisely so a DID does not travel with the payload.
        # Sending the principals instead would put usernames into a `QueryExecuted`
        # provenance event, which rulebook `L-3` limits to codes, pseudonymous
        # DIDs and hashes. The field is the PDP's to fill, not this one's.
        authorized_subject_ids=None,
    )
    return _page(rows, body)


def _apply_row_filter(
    rows: list[dict[str, Any]], row_filter: DataplaneRowFilter
) -> list[dict[str, Any]]:
    """Narrow `rows` to the ones the filter admits.

    The filter arrives whole — handler, args and principals — because the
    handler is what knows how a principal maps to values in the column. This
    service implements one handler; the real dataset-api registers several
    through `celine.dataset...row_filters`.

    **An unimplemented handler withholds every row.** It is not a permission to
    serve unfiltered: an *allow* carrying a filter says "these rows", and a PEP
    that cannot work out which rows has not been told it may serve them all.
    That is the whole failure this shape exists to prevent — the previous reading
    (`row_filter["column"]`) matched no key the connector sends, so the request
    died as a 500 with the narrowing never applied.
    """
    if row_filter.handler != DIRECT_USER_MATCH:
        log.warning(
            "No implementation for row filter handler %r — withholding every row",
            row_filter.handler,
        )
        raise HTTPException(
            403,
            f"Cannot enforce row filter handler {row_filter.handler!r}: "
            "this data plane implements no such handler, so no rows may be served",
        )

    column = row_filter.args.get("column")
    if not column:
        raise HTTPException(
            403,
            f"Row filter handler {row_filter.handler!r} names no column to filter on",
        )

    # An empty principal set narrows to nothing. It never widens to everything:
    # ds denies before sending one, and reading it as "no filter" is precisely
    # how a consent-gated dataset leaks.
    principals = set(row_filter.principals)
    return [row for row in rows if row.get(column) in principals]


_jwks_cache: dict[str, Any] = {}


async def _verified_consumer(bearer: str | None) -> str:
    """The consumer DID this request proves, from the EDR token's ``aud``.

    **Nothing else validates this token.** The EDC data-plane proxy was removed
    upstream (`data-plane-public-api-v2`, deprecated), so the EDR endpoint we
    hand out *is* this service — there is no proxy in front to check the
    signature. And the token carries no ``exp``
    (`DataPlaneAuthorizationServiceImpl.createTokenParams` at v0.16.0), so a
    leaked one is valid until the agreement behind it is revoked. Verifying it
    here is the only thing standing between a bearer string and somebody's data.

    ``aud`` is the one identity fact that must never come from a header: it is
    what ds checks the agreement against.
    """
    if not settings.verify_edr:
        # Dev escape hatch, off by default and refused in production by the
        # guard above — it exists so a stack without a reachable EDC JWKS can
        # still be brought up, not so a deployment can skip verification.
        return _unverified_aud(bearer)

    token = (bearer or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Dataspace mode requires the EDR token")

    claims = None
    for key in await _verification_keys():
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["ES256", "RS256"],
                options={"verify_aud": False, "verify_exp": False},
            )
            break
        except Exception:  # noqa: BLE001 — try the next key, refuse if none fit
            continue
    if claims is None:
        # Every key in the set is tried rather than the one matching `kid`: EDC
        # sets `kid` to its **vault alias** (`participant-private-key`) while the
        # JWK carries its own (`edr-provider-key-1`), so a kid-indexed lookup
        # never matches. The set is one or two keys, so trying them all costs
        # nothing and survives a rotation that changes either name.
        raise HTTPException(401, "EDR token is not valid")

    audience = claims.get("aud")
    if isinstance(audience, list):
        audience = audience[0] if audience else None
    if not audience:
        raise HTTPException(401, "EDR token names no audience")
    return str(audience)


def _unverified_aud(bearer: str | None) -> str:
    token = (bearer or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Dataspace mode requires the EDR token")
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "EDR token is not a JWT") from exc
    audience = claims.get("aud")
    if isinstance(audience, list):
        audience = audience[0] if audience else None
    if not audience:
        raise HTTPException(401, "EDR token names no audience")
    log.warning("EDR signature NOT verified — DATASET_API_VERIFY_EDR is off")
    return str(audience)


async def _verification_keys() -> list[Any]:
    """The provider's EDR signing keys, via ds.

    ds serves the public half of the vault key EDC signs with
    (`/internal/edr-jwks`), so this service never needs the EDC vault or the
    management credential. Cached after the first fetch; a verification failure
    clears the cache so a rotation does not need a restart.
    """
    from jwt import PyJWK

    if _jwks_cache.get("keys"):
        return _jwks_cache["keys"]

    url = f"{settings.connector_internal_url.rstrip('/')}/internal/edr-jwks"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url, headers=await _internal_headers())
    response.raise_for_status()

    keys = []
    for entry in response.json().get("keys", []):
        try:
            keys.append(PyJWK.from_dict({**entry, "alg": entry.get("alg", "ES256")}).key)
        except Exception:  # noqa: BLE001 — an unusable key is not a fatal one
            log.warning("Unusable JWK in the EDR key set: %s", entry.get("kid"))
    if not keys:
        raise HTTPException(503, "ds published no usable EDR verification key")
    _jwks_cache["keys"] = keys
    return keys


async def _authorize(
    *,
    consumer_did: str,
    agreement_id: str,
    transfer_id: str | None,
    purpose: list[str],
    dataset_ids: list[str],
) -> DataplaneDecision:
    """Ask ds whether rows may flow, and which.

    One call, one decision. This service assembles nothing: agreement validity,
    the agreement↔consumer binding, purpose admissibility and the consent pool
    are all ds's to answer, because ds is the control plane.

    The answer is parsed as `ds.governance.DataplaneDecision` — the shared shape,
    so a change on the connector side that this service has not caught up with
    fails here rather than downstream of the narrowing.
    """
    url = f"{settings.connector_internal_url.rstrip('/')}/internal/dataplane/authorize"
    payload = {
        "consumer_did": consumer_did,
        "agreement_id": agreement_id,
        "transfer_id": transfer_id,
        "purpose": purpose,
        "dataset_ids": dataset_ids,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=await _internal_headers())
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"ds-connector refused the check: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        # ds unreachable is a denial, never an allow: the control plane not
        # answering is exactly when the data plane must not improvise.
        raise HTTPException(502, "ds-connector unreachable") from exc
    try:
        return DataplaneDecision.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        # A decision we cannot read is a decision we did not receive. The
        # tempting alternative — read the keys we recognise and ignore the rest —
        # is what serves rows past a narrowing that arrived under a new name.
        log.error("Unreadable decision from ds-connector: %s", exc)
        raise HTTPException(502, "ds-connector returned an unreadable decision") from exc


async def _internal_headers() -> dict[str, str]:
    """Authenticate to ds-connector's ``/internal/*`` API as this service.

    ``svc-ds-dataset-api`` holds ``connector.internal`` with ``svc-ds-connector``
    in its audience. This replaced the ``X-Api-Key`` the PEP used to send: that
    key is the *same* value as EDC's Management API key, so one leak yielded
    contract administration, the data-plane signing keys behind
    ``/internal/edr-jwks`` and the subject pools behind
    ``/internal/consent/check`` at once — and every caller arrived as the same
    anonymous bearer, so no audit trail could tell the dataset-api from the EDC.

    No fallback: the connector no longer accepts that header, so one could only
    turn a clear configuration error into a 403 at query time.
    """
    return {"Authorization": f"Bearer {await _token_provider()}"}


async def _audit_query(
    dataset_id: str,
    consumer_id: str | None,
    subject_id: str | None,
    agreement_id: str | None,
    transfer_id: str | None,
    row_count: int,
    authorized_subject_ids: list[str] | None,
) -> None:
    url = f"{settings.connector_internal_url.rstrip('/')}/internal/audit/query"
    payload = {
        "dataset_id": dataset_id,
        "consumer_id": consumer_id,
        "user_id": subject_id,
        "subject_id": subject_id,
        "agreement_id": agreement_id,
        "transfer_id": transfer_id,
        "row_count": row_count,
        "authorized_subject_ids": authorized_subject_ids,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload, headers=await _internal_headers())
    except httpx.RequestError:
        return


async def _query_external(spec: dict[str, Any]) -> list[dict[str, Any]]:
    if not settings.external_query_url:
        raise HTTPException(503, "DATASET_API_EXTERNAL_QUERY_URL is not configured")

    payload = {
        "sql": spec["external_sql"],
        "limit": spec.get("external_limit", 50),
        "offset": 0,
        "skip_count": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.external_query_url.rstrip('/')}/query",
                json=payload,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            exc.response.status_code,
            f"External dataset-api error: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"External dataset-api unreachable: {exc}") from exc

    body = response.json()
    rows = list(body.get("items") or [])
    subject_column = spec.get("subject_column")
    subject_id = spec.get("subject_id")
    if subject_column and subject_id:
        rows = [{**row, subject_column: subject_id} for row in rows]
    return rows


