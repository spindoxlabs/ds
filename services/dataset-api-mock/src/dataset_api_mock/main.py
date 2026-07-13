from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic_settings import BaseSettings, SettingsConfigDict

from .metrics import install_metrics


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATASET_API_", extra="ignore")

    connector_internal_url: str = "http://ds-connector:30001"
    enforce_consent: bool = True
    external_query_url: str | None = None
    extra_datasets_path: str | None = None


settings = Settings()
app = FastAPI(title="dataset-api-mock", version="0.1.0")
install_metrics(app, "dataset-api")


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
            {"timestamp": "2026-05-11T08:00:00Z", "sub": "subject-001", "meter_id": "MTR-001", "kwh": 0.42},
            {"timestamp": "2026-05-11T08:15:00Z", "sub": "subject-001", "meter_id": "MTR-001", "kwh": 0.37},
            {"timestamp": "2026-05-11T08:00:00Z", "sub": "subject-002", "meter_id": "MTR-002", "kwh": 0.55},
            {"timestamp": "2026-05-11T08:15:00Z", "sub": "subject-002", "meter_id": "MTR-002", "kwh": 0.51},
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


@app.api_route("/query", methods=["GET", "POST"])
async def query(
    request: Request,
    dataset_name: str = Query(default="datasets.gold.om_weather_features"),
    consumer_id: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    agreement_id: str | None = Query(default=None),
    transfer_id: str | None = Query(default=None),
) -> dict[str, Any]:
    if request.method == "POST":
        body = await request.json()
        dataset_name = body.get("dataset_name", dataset_name)
        consumer_id = body.get("consumer_id", consumer_id)
        subject_id = body.get("subject_id", subject_id)
        agreement_id = body.get("agreement_id", agreement_id)
        transfer_id = body.get("transfer_id", transfer_id)

    spec = DATASETS.get(dataset_name)
    if not spec:
        raise HTTPException(404, f"Unknown dataset {dataset_name!r}")
    if not _dataset_enabled(spec):
        raise HTTPException(404, f"Dataset {dataset_name!r} is not enabled in this runtime profile")

    rows = (
        await _query_external(spec)
        if spec.get("source") == "external"
        else list(spec["rows"])
    )
    authorization: dict[str, Any] = {
        "dataset_name": dataset_name,
        "requires_consent": spec["requires_consent"],
        "consumer_id": consumer_id,
        "agreement_id": agreement_id,
        "transfer_id": transfer_id,
        "consent_checked": False,
        "authorized_subject_ids": None,
    }

    if transfer_id:
        transfer_active = await _transfer_active(transfer_id, agreement_id)
        authorization["transfer_active"] = transfer_active
        if transfer_active is False:
            raise HTTPException(403, "Transfer is not active")

    if agreement_id:
        authorization["agreement_active"] = await _agreement_active(agreement_id)
        if authorization["agreement_active"] is False:
            raise HTTPException(403, "Contract agreement is not active")

    if settings.enforce_consent and spec["requires_consent"]:
        if not consumer_id:
            raise HTTPException(
                403,
                "consumer_id is required for consent-protected datasets in mock mode",
            )
        subject_ids = await _granted_subject_ids(dataset_name, spec["asset_id"], consumer_id, subject_id)
        subject_column = spec.get("subject_column", "sub")
        rows = [row for row in rows if row.get(subject_column) in subject_ids]
        authorization["consent_checked"] = True
        authorization["authorized_subject_ids"] = subject_ids

    await _audit_query(
        dataset_id=spec["asset_id"],
        consumer_id=consumer_id,
        subject_id=subject_id,
        agreement_id=agreement_id,
        transfer_id=transfer_id,
        row_count=len(rows),
        authorized_subject_ids=authorization["authorized_subject_ids"],
    )

    return {
        "dataset_name": dataset_name,
        "count": len(rows),
        "rows": rows,
        "authorization": authorization,
    }


async def _agreement_active(agreement_id: str) -> bool | None:
    url = f"{settings.connector_internal_url.rstrip('/')}/internal/agreements/{agreement_id}/status"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return bool(response.json().get("active"))
    except httpx.RequestError:
        return None


async def _transfer_active(transfer_id: str, agreement_id: str | None) -> bool | None:
    url = f"{settings.connector_internal_url.rstrip('/')}/internal/transfers/{transfer_id}/status"
    params = {"agreement_id": agreement_id} if agreement_id else None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
        return bool(response.json().get("active"))
    except httpx.RequestError:
        return None


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
            await client.post(url, json=payload)
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


async def _granted_subject_ids(
    dataset_name: str,
    asset_id: str,
    consumer_id: str,
    subject_id: str | None,
) -> list[str]:
    candidates = [dataset_name, asset_id]
    async with httpx.AsyncClient(timeout=5.0) as client:
        for dataset_id in candidates:
            params = {"dataset_id": dataset_id, "consumer_id": consumer_id}
            if subject_id:
                params["subject_id"] = subject_id
            try:
                response = await client.get(
                    f"{settings.connector_internal_url.rstrip('/')}/internal/consent/check",
                    params=params,
                )
                response.raise_for_status()
            except httpx.RequestError:
                continue
            body = response.json()
            if subject_id and body.get("consent_active"):
                return [subject_id]
            subject_ids = body.get("subject_ids") or []
            if subject_ids:
                return subject_ids
    return []
