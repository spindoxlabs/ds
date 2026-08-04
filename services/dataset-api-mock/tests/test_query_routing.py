"""Which datasets a statement selects, and which path serves them.

Three decisions are taken before any authorization happens, and each was wrong
in a way that no later check could recover:

* the **plain path** served consent-gated rows to anyone who omitted a header;
* **substring matching** let a comment or a literal choose the dataset the
  decision would be about;
* a statement naming several datasets was authorised for all and served as one.

All three are settled here rather than in `test_query_enforcement.py`, because
none of them involves a decision — they are about what the request *is*.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dataset_api_mock import main
from dataset_api_mock.main import _datasets_in_sql

GATED = "datasets.silver.meters_15m"
OPEN = "datasets.gold.om_weather_features"


@pytest.fixture
def client():
    return TestClient(main.app)


def _plain(client, sql: str):
    """A query with no `Edc-Contract-Agreement-Id`: the non-dataspace path."""
    return client.post("/query", json={"sql": sql, "limit": 100})


# ── The plain path ─────────────────────────────────────────────────────────────


def test_the_plain_path_refuses_a_consent_gated_dataset(client):
    """The P0.

    Omitting one header returned every row of a `requires_consent: true` dataset
    — no token, no decision, no audit event. The header is the caller's to send,
    so the consent gate was opt-in for the party it exists to constrain.
    """
    response = _plain(client, f"SELECT * FROM {GATED}")
    assert response.status_code == 403
    assert GATED in response.json()["detail"]


def test_the_plain_path_leaks_no_rows_while_refusing(client):
    """Not a filtered result, not an empty page — no body of rows at all.

    Worth separating: a refusal that still carries `items` would satisfy a status
    assertion and serve the data anyway.
    """
    assert "items" not in _plain(client, f"SELECT * FROM {GATED}").json()


def test_the_plain_path_still_serves_an_open_dataset(client):
    """The non-dataspace deployment is not what this change is aimed at.

    A dataset with no data subject behind it has nothing for ds to decide, and
    breaking that path would make the fix a migration rather than a fix.
    """
    response = _plain(client, f"SELECT * FROM {OPEN}")
    assert response.status_code == 200
    assert response.json()["count"] == 3


# ── Which datasets the statement names ────────────────────────────────────────


def test_a_comment_does_not_select_a_dataset():
    """`-- see datasets.silver.meters_15m` used to name it.

    That string decides which asset id goes to `authorize`, so it decides which
    agreement and which consent pool answer. A caller who can steer it chooses
    the dataset the decision is about while reading from another.
    """
    assert _datasets_in_sql(f"SELECT * FROM {OPEN} -- see {GATED}") == [OPEN]


def test_a_block_comment_does_not_select_a_dataset():
    assert _datasets_in_sql(f"/* {GATED} */ SELECT * FROM {OPEN}") == [OPEN]


def test_a_string_literal_does_not_select_a_dataset():
    assert _datasets_in_sql(f"SELECT * FROM {OPEN} WHERE note = '{GATED}'") == [OPEN]


def test_a_longer_identifier_does_not_select_a_dataset():
    """`datasets.silver.meters_15m_v2` is a different table and may be anyone's."""
    assert _datasets_in_sql(f"SELECT * FROM {GATED}_v2") == []


def test_a_qualified_identifier_does_not_select_a_dataset():
    """A dot on either side means the name is a *part* of something else."""
    assert _datasets_in_sql(f"SELECT * FROM warehouse.{GATED}") == []


def test_a_quoted_identifier_still_selects_it():
    """Double quotes are SQL's identifier quoting, so this is a real reference.

    Stripping them along with the literals would have made a legitimate query
    unresolvable — the fix must narrow what counts as a reference, not what
    counts as SQL.
    """
    assert _datasets_in_sql(f'SELECT * FROM "{GATED}"') == [GATED]


def test_an_ordinary_reference_still_selects_it():
    assert _datasets_in_sql(f"SELECT * FROM {GATED} WHERE kwh > 0") == [GATED]


# ── One statement, one dataset ────────────────────────────────────────────────


def test_a_statement_naming_two_datasets_is_refused(client):
    """It used to authorise both and serve `dataset_names[0]`.

    Silently: the rows came from one dataset, the audit event named that one, and
    the decision covered two. Refusing says this plane cannot execute a join;
    picking the first says nothing and looks like an answer.
    """
    response = _plain(client, f"SELECT * FROM {OPEN} JOIN {GATED} USING (timestamp)")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert GATED in detail and OPEN in detail


def test_a_statement_naming_no_known_dataset_is_refused(client):
    assert _plain(client, "SELECT 1").status_code == 400


# ── The subject's own inventory view ──────────────────────────────────────────


def test_a_subject_sees_the_dataset_holding_their_rows(client):
    """`GET /subjects/{did}/datasets` is what the portal's *my-data* page calls.

    It compared the DID to the subject column directly, which worked only while
    the rows were keyed by DID. Once they are keyed by device — as governance
    declares and as the real dataset-api holds them — the comparison finds
    nothing and the page tells the person they own no data. Resolving through the
    handler is the same hop `_apply_row_filter` makes, for the same reason.
    """
    did = "did:web:rec.dataspaces.localhost:users:data-subject"
    owned = client.get(f"/subjects/{did}/datasets").json()["datasets"]
    assert [d["name"] for d in owned] == [GATED]
    assert owned[0]["subject_column"] == "device_id"
    assert owned[0]["sample_rows"] == 2


def test_a_subject_sees_nothing_of_anyone_elses(client):
    """Including the rows the negative-control device holds."""
    did = "did:web:rec.dataspaces.localhost:users:outsider"
    assert client.get(f"/subjects/{did}/datasets").json()["datasets"] == []
