from __future__ import annotations

import logging
from typing import Any

import httpx
import psycopg

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient

log = logging.getLogger(__name__)


class CleanupIncomplete(RuntimeError):
    """A clean that could not do everything it was asked to.

    Raised rather than logged so `ds-e2e clean` and `e2e:prepare` stop, instead
    of handing the next run a stack still holding the previous one's agreements
    — which surfaces as an unrelated flow failing on stale state.
    """

# The EDC management credentials and endpoints (`E2E-07`).
#
# Hardcoded module constants until now, so a stack whose EDC key or ports were
# changed could not be cleaned — and `run_cleanup` reported success having
# deleted nothing, because a 401 on a delete is not something it checked. Every
# other address the harness uses is a setting; these are now too, with the same
# dev defaults so nothing changes for a default stack.

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
    "connector_rec": CONNECTOR_TABLES,
    "connector_third_party": CONNECTOR_TABLES,
    # The second provider (`DID-15`). A stack left out of the clean is a stack
    # whose previous run's agreements survive into the next one, which is the
    # quietest possible way for a suite to stop meaning what it says.
    "connector_grid_operator": CONNECTOR_TABLES,
    "provenance_rec": PROVENANCE_TABLES,
    "provenance_third_party": PROVENANCE_TABLES,
    "provenance_grid_operator": PROVENANCE_TABLES,
}

# EDC stores are dropped and recreated rather than truncated: their schema is
# owned by the connector runtime, so the table set is not ours to enumerate.
EDC_DATABASES = ("edc_rec", "edc_third_party", "edc_grid_operator")

EDC_CONTEXT = {"@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"}, "@type": "QuerySpec"}


def edc_headers(settings: E2ESettings) -> dict[str, str]:
    return {"x-api-key": settings.edc_api_key, "Content-Type": "application/json"}


def edc_management_urls(settings: E2ESettings) -> dict[str, str]:
    """Control-plane management endpoints, by role."""
    return {
        "provider": settings.edc_provider_management_url,
        "consumer": settings.edc_consumer_management_url,
        "grid-operator": settings.edc_grid_operator_management_url,
    }


def provider_sync_targets(settings: E2ESettings) -> list[tuple[str, str]]:
    """Every connector that must re-sync its catalogue after a clean.

    A list, not a literal inside ``run_cleanup``, because the count is the thing
    that goes stale: `DID-15` added the second provider and the cleanup grew a
    second sync, while the tests kept asserting ``assert_called_once`` and were
    red on `main` for it. A test that asserts against this function stays true
    when a third provider arrives, and fails when one is added to the topology
    and not to the clean.
    """
    return [
        (settings.connector_url, "provider"),
        (settings.grid_operator_connector_url, "grid-operator"),
    ]


def _edc_list(
    client: httpx.Client, mgmt_url: str, resource: str, headers: dict[str, str]
) -> list[dict[str, Any]]:
    resp = client.post(
        f"{mgmt_url}/v3/{resource}/request", json=EDC_CONTEXT, headers=headers
    )
    return resp.json() if resp.status_code == 200 and resp.text else []


def _edc_terminate(
    client: httpx.Client, mgmt_url: str, resource: str, item_id: str,
    body_type: str, headers: dict[str, str],
) -> None:
    client.post(
        f"{mgmt_url}/v3/{resource}/{item_id}/terminate",
        json={
            "@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"},
            "@type": body_type,
            "reason": "e2e cleanup",
        },
        headers=headers,
    )


def _clear_edc(
    client: httpx.Client, mgmt_url: str, label: str, settings: E2ESettings
) -> None:
    headers = edc_headers(settings)

    # Terminate active transfer processes first (block agreement cleanup)
    transfers = _edc_list(client, mgmt_url, "transferprocesses", headers)
    for tp in transfers:
        tp_id = tp.get("@id", "")
        state = tp.get("edc:state", tp.get("state", ""))
        if state not in ("TERMINATED", "COMPLETED"):
            _edc_terminate(client, mgmt_url, "transferprocesses", tp_id, "TerminateTransfer", headers)
    if transfers:
        log.info("Terminated %d transfers (%s)", len(transfers), label)

    # Terminate active negotiations
    negotiations = _edc_list(client, mgmt_url, "contractnegotiations", headers)
    for neg in negotiations:
        neg_id = neg.get("@id", "")
        state = neg.get("edc:state", neg.get("state", ""))
        if state not in ("TERMINATED",):
            _edc_terminate(client, mgmt_url, "contractnegotiations", neg_id, "TerminateNegotiation", headers)
    if negotiations:
        log.info("Terminated %d negotiations (%s)", len(negotiations), label)

    # Delete contract definitions, policy definitions, assets (in dependency order)
    for resource in ("contractdefinitions", "policydefinitions", "assets"):
        items = _edc_list(client, mgmt_url, resource, headers)
        for item in items:
            client.delete(f"{mgmt_url}/v3/{resource}/{item.get('@id', '')}", headers=headers)
        if items:
            log.info("Deleted %d %s (%s)", len(items), resource, label)


def run_cleanup(
    settings: E2ESettings,
    http: HttpClient,
    edc_client: httpx.Client | None = None,
) -> None:
    """Reset the dataspace to a known state. **Destructive, by design.**

    `edc_client` is a parameter because it used to be a `httpx.Client()`
    constructed here, and a caller that mocked `http` and `psycopg` still got a
    live one (`E2E-17`). The unit suite did exactly that: eight green tests in
    `test_cleanup.py` called this function and **deleted every contract
    definition and policy from the running dev stack's EDCs**, on both
    providers, while asserting on mocks.

    The symptom was three sessions of debugging a federated catalogue that had
    gone empty on its own — the assets survived, because the asset delete 409s
    while an agreement references it, so the wreckage looked like a half-run
    provider sync rather than a clean. Nothing in any service log accounted for
    it: the deletes go straight to the EDC Management API.

    Two things follow, and the second is the one that generalises:

    - The client is injected, so a test can supply one that goes nowhere.
    - `tests/conftest.py` refuses **any** outbound socket in the unit suite. A
      unit suite that can reach the network will eventually change something,
      and no amount of care at each call site prevents the next instance.
    """
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

    for edc_db in EDC_DATABASES:
        pg_dsn = f"{base_url}/postgres"
        try:
            with psycopg.connect(pg_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DROP DATABASE IF EXISTS {edc_db}")
                    cur.execute(f"CREATE DATABASE {edc_db}")
            log.info("Reset EDC database %s", edc_db)
        except psycopg.Error as exc:
            log.warning("Could not reset %s: %s", edc_db, exc)

    owns_client = edc_client is None
    edc_client = edc_client or httpx.Client(timeout=10)
    failures: list[str] = []
    try:
        for label, mgmt_url in edc_management_urls(settings).items():
            try:
                _clear_edc(edc_client, mgmt_url, label, settings)
            except Exception as exc:
                # Logged **and collected**. This used to warn and continue, and
                # `run_cleanup` then returned normally — so `Cleanup complete`
                # was printed over three control planes that had not been
                # cleaned, and the next run's flows failed on the previous run's
                # agreements with no connection to the cause.
                #
                # Found exactly that way: threading settings through these calls
                # left one call site unfixed, every unit test stayed green, and
                # the live clean printed three warnings and then `Cleanup
                # complete`. A warning nobody has to act on is not a result.
                log.warning("EDC cleanup failed (%s): %s", label, exc)
                failures.append(f"{label}: {exc}")
    finally:
        # Only what this function opened. Closing a caller's client would break
        # the next use of it, and the caller is the one that knows its lifetime.
        if owns_client:
            edc_client.close()

    # **Both providers re-sync.** Dropping an EDC's database empties its
    # catalogue, so a provider that is not re-synced afterwards is a provider
    # with nothing to negotiate for — and the failure surfaces as "asset not
    # found" in whichever flow happens to reach it first (`DID-15`).
    token_headers = http.bearer_headers()
    for url, label in provider_sync_targets(settings):
        try:
            http.post(f"{url}/provider/sync", {}, headers=token_headers)
            log.info("Provider sync completed (%s)", label)
        except Exception as exc:
            log.warning("Provider sync after cleanup failed (%s): %s", label, exc)
            failures.append(f"provider sync {label}: {exc}")

    if failures:
        raise CleanupIncomplete(
            "cleanup did not finish; the next run starts on state this did not "
            "remove:\n  " + "\n  ".join(failures)
        )
