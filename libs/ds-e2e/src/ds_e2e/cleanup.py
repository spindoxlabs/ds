from __future__ import annotations

import logging

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


def run_cleanup(settings: E2ESettings, http: HttpClient) -> None:
    """Reset the dataspace to a known state. **Destructive, by design.**

    **No EDC management calls.** This used to also terminate every transfer and
    negotiation and delete every definition through each EDC's management API,
    with the shared key. Both are gone: the management port is not published
    and there is no key (plan `the-management-api-is-v3-behind-one-key`,
    decision 1). The calls were also redundant — the EDC databases are dropped
    and recreated below, and `e2e:prepare` restarts all three EDCs straight
    afterwards, which is what empties their stores.

    `tests/conftest.py` refuses any outbound socket in the unit suite: a
    `run_cleanup` that built its own HTTP client once deleted every contract
    definition from the running dev stack while its tests asserted on mocks
    (`E2E-17`). Keep every network path injectable.
    """
    base_url = settings.database_url.rstrip("/")
    failures: list[str] = []

    for db_name, tables in DATABASES.items():
        dsn = f"{base_url}/{db_name}"
        try:
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    table_list = ", ".join(tables)
                    cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
                conn.commit()
            log.info("Truncated %s: %s", db_name, ", ".join(tables))
        except psycopg.Error as exc:
            # Collected, not merely warned — see `_clear_edc` below, which was
            # given this treatment first. A state reset that did not happen is
            # the same result whichever store refused.
            log.warning("Could not truncate %s: %s", db_name, exc)
            failures.append(f"truncate {db_name}: {exc}")

    for edc_db in EDC_DATABASES:
        pg_dsn = f"{base_url}/postgres"
        try:
            with psycopg.connect(pg_dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    # **Terminate the connectors' sessions first, or the drop
                    # cannot happen.** The three EDC control planes hold open
                    # pools against exactly these databases, and PostgreSQL
                    # refuses `DROP DATABASE` while any session is attached:
                    # *"database is being accessed by other users … There are 3
                    # other sessions"*. Without this the drop raised, the
                    # handler below warned, `run_cleanup` returned normally, and
                    # every flow then ran against the **previous** run's
                    # agreements — which is how two flows spent a session
                    # unattributed: the provider denied them in
                    # `policy.monitor`, correctly, on a stale agreement whose
                    # consent row the truncate above had just removed.
                    #
                    # Safe because the database is being dropped on the next
                    # line, and `e2e:prepare` restarts all three EDCs
                    # immediately afterwards — that restart is not optional and
                    # says so.
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (edc_db,),
                    )
                    cur.execute(f"DROP DATABASE IF EXISTS {edc_db}")
                    cur.execute(f"CREATE DATABASE {edc_db}")
            log.info("Reset EDC database %s", edc_db)
        except psycopg.Error as exc:
            log.warning("Could not reset %s: %s", edc_db, exc)
            failures.append(f"reset {edc_db}: {exc}")

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
