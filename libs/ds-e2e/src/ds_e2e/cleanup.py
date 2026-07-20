from __future__ import annotations

import logging

import httpx
import psycopg

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient

log = logging.getLogger(__name__)

EDC_API_KEY = "insecure-dev-key"

CONNECTOR_TABLES = [
    "consumer_access_requests",
    "consumer_transfers",
    "contract_agreements",
    "consent_requests",
]

PROVENANCE_TABLES = [
    "domain_events",
    "prov_relations",
    "prov_nodes",
    "access_log",
]

DATABASES = {
    "connector_provider": CONNECTOR_TABLES,
    "connector_consumer": CONNECTOR_TABLES,
    "provenance_provider": PROVENANCE_TABLES,
    "provenance_consumer": PROVENANCE_TABLES,
}

EDC_PROVIDER_MGMT = "http://172.17.0.1:19193/management"
EDC_CONSUMER_MGMT = "http://172.17.0.1:29193/management"

EDC_CONTEXT = {"@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"}, "@type": "QuerySpec"}
EDC_HEADERS = {"x-api-key": EDC_API_KEY, "Content-Type": "application/json"}


def _edc_list(client: httpx.Client, mgmt_url: str, resource: str) -> list[dict]:
    resp = client.post(f"{mgmt_url}/v3/{resource}/request", json=EDC_CONTEXT, headers=EDC_HEADERS)
    return resp.json() if resp.status_code == 200 and resp.text else []


def _edc_terminate(client: httpx.Client, mgmt_url: str, resource: str, item_id: str, body_type: str) -> None:
    client.post(
        f"{mgmt_url}/v3/{resource}/{item_id}/terminate",
        json={
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": body_type,
            "reason": "e2e cleanup",
        },
        headers=EDC_HEADERS,
    )


def _clear_edc(client: httpx.Client, mgmt_url: str, label: str) -> None:
    headers = {"x-api-key": EDC_API_KEY}

    # Terminate active transfer processes first (block agreement cleanup)
    transfers = _edc_list(client, mgmt_url, "transferprocesses")
    for tp in transfers:
        tp_id = tp.get("@id", "")
        state = tp.get("edc:state", tp.get("state", ""))
        if state not in ("TERMINATED", "COMPLETED"):
            _edc_terminate(client, mgmt_url, "transferprocesses", tp_id, "TerminateTransfer")
    if transfers:
        log.info("Terminated %d transfers (%s)", len(transfers), label)

    # Terminate active negotiations
    negotiations = _edc_list(client, mgmt_url, "contractnegotiations")
    for neg in negotiations:
        neg_id = neg.get("@id", "")
        state = neg.get("edc:state", neg.get("state", ""))
        if state not in ("TERMINATED",):
            _edc_terminate(client, mgmt_url, "contractnegotiations", neg_id, "TerminateNegotiation")
    if negotiations:
        log.info("Terminated %d negotiations (%s)", len(negotiations), label)

    # Delete contract definitions, policy definitions, assets (in dependency order)
    for resource in ("contractdefinitions", "policydefinitions", "assets"):
        items = _edc_list(client, mgmt_url, resource)
        for item in items:
            client.delete(f"{mgmt_url}/v3/{resource}/{item.get('@id', '')}", headers=headers)
        if items:
            log.info("Deleted %d %s (%s)", len(items), resource, label)


def run_cleanup(settings: E2ESettings, http: HttpClient) -> None:
    base_url = settings.database_url.rstrip("/")

    for db_name, tables in DATABASES.items():
        dsn = f"{base_url}/{db_name}"
        try:
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    table_list = ", ".join(tables)
                    cur.execute(
                        f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"
                    )
                conn.commit()
            log.info("Truncated %s: %s", db_name, ", ".join(tables))
        except psycopg.Error as exc:
            log.warning("Could not truncate %s: %s", db_name, exc)

    for edc_db in ("edc_provider", "edc_consumer"):
        pg_dsn = f"{base_url}/postgres"
        try:
            with psycopg.connect(pg_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DROP DATABASE IF EXISTS {edc_db}")
                    cur.execute(f"CREATE DATABASE {edc_db}")
            log.info("Reset EDC database %s", edc_db)
        except psycopg.Error as exc:
            log.warning("Could not reset %s: %s", edc_db, exc)

    edc_client = httpx.Client(timeout=10)
    try:
        for mgmt_url, label in [
            (EDC_PROVIDER_MGMT, "provider"),
            (EDC_CONSUMER_MGMT, "consumer"),
        ]:
            try:
                _clear_edc(edc_client, mgmt_url, label)
            except Exception as exc:
                log.warning("EDC cleanup failed (%s): %s", label, exc)
    finally:
        edc_client.close()

    try:
        token_headers = http.bearer_headers()
        http.post(
            f"{settings.connector_url}/provider/sync", {}, headers=token_headers
        )
        log.info("Provider sync completed")
    except Exception as exc:
        log.warning("Provider sync after cleanup failed: %s", exc)
