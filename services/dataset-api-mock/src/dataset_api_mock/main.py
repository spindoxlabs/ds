from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATASET_API_", extra="ignore")

    connector_internal_url: str = "http://ds-connector:30001"
    enforce_consent: bool = True
    celine_url: str | None = None


settings = Settings()
app = FastAPI(title="dataset-api-mock", version="0.1.0")


DATASETS: dict[str, dict[str, Any]] = {
    "datasets.gold.om_weather_features": {
        "asset_id": "https://provider.dataspaces.localhost/datasets/om_weather_features",
        "requires_consent": False,
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "location": "EC-001", "temperature_c": 18.7, "wind_ms": 2.8, "ghi": 426},
            {"timestamp": "2026-05-11T08:15:00Z", "location": "EC-001", "temperature_c": 18.9, "wind_ms": 2.6, "ghi": 441},
            {"timestamp": "2026-05-11T08:30:00Z", "location": "EC-001", "temperature_c": 19.1, "wind_ms": 2.5, "ghi": 455},
        ],
    },
    "datasets.silver.meters_15m": {
        "asset_id": "https://provider.dataspaces.localhost/datasets/datasets/silver/meters_15m",
        "requires_consent": True,
        "subject_column": "sub",
        "rows": [
            {"timestamp": "2026-05-11T08:00:00Z", "sub": "subject-001", "meter_id": "MTR-001", "kwh": 0.42},
            {"timestamp": "2026-05-11T08:15:00Z", "sub": "subject-001", "meter_id": "MTR-001", "kwh": 0.37},
            {"timestamp": "2026-05-11T08:00:00Z", "sub": "subject-002", "meter_id": "MTR-002", "kwh": 0.55},
            {"timestamp": "2026-05-11T08:15:00Z", "sub": "subject-002", "meter_id": "MTR-002", "kwh": 0.51},
        ],
    },
    "datasets.celine.folgaria_weather_hourly": {
        "asset_id": "http://api.celine.localhost/datasets/dataset/datasets.ds_dev_gold.folgaria_weather_hourly",
        "requires_consent": True,
        "subject_column": "subject_id",
        "subject_id": "ah-00003",
        "source": "celine",
        "celine_sql": (
            "select ts, location_id, temp, humidity "
            "from ds_dev_gold.folgaria_weather_hourly "
            "order by ts desc"
        ),
        "celine_limit": 12,
        "rows": [],
    },
}


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
            for name, spec in DATASETS.items()
        ]
    }


@app.get("/catalogue")
async def catalogue() -> dict[str, list[dict[str, Any]]]:
    return {"datasets": [_catalogue_entry(name, spec) for name, spec in DATASETS.items()]}


@app.get("/catalogue/{asset_id:path}")
async def catalogue_item(asset_id: str) -> dict[str, Any]:
    for name, spec in DATASETS.items():
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
) -> dict[str, Any]:
    if request.method == "POST":
        body = await request.json()
        dataset_name = body.get("dataset_name", dataset_name)
        consumer_id = body.get("consumer_id", consumer_id)
        subject_id = body.get("subject_id", subject_id)
        agreement_id = body.get("agreement_id", agreement_id)

    spec = DATASETS.get(dataset_name)
    if not spec:
        raise HTTPException(404, f"Unknown dataset {dataset_name!r}")

    rows = (
        await _query_celine(spec)
        if spec.get("source") == "celine"
        else list(spec["rows"])
    )
    authorization: dict[str, Any] = {
        "dataset_name": dataset_name,
        "requires_consent": spec["requires_consent"],
        "consumer_id": consumer_id,
        "agreement_id": agreement_id,
        "consent_checked": False,
        "authorized_subject_ids": None,
    }

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


async def _query_celine(spec: dict[str, Any]) -> list[dict[str, Any]]:
    if not settings.celine_url:
        raise HTTPException(503, "DATASET_API_CELINE_URL is not configured")

    payload = {
        "sql": spec["celine_sql"],
        "limit": spec.get("celine_limit", 50),
        "offset": 0,
        "skip_count": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.celine_url.rstrip('/')}/query",
                json=payload,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            exc.response.status_code,
            f"CELINE dataset-api error: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"CELINE dataset-api unreachable: {exc}") from exc

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
