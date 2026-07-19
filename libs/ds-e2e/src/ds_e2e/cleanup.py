from __future__ import annotations

import logging

import psycopg

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient

log = logging.getLogger(__name__)

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

    try:
        token_headers = http.bearer_headers()
        http.post(
            f"{settings.connector_url}/provider/sync", {}, headers=token_headers
        )
        log.info("Provider sync completed")
    except Exception as exc:
        log.warning("Provider sync after cleanup failed: %s", exc)
