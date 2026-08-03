"""What a dataset must say about itself, and whether it says the same as ds.

Two separate failures live here.

**A fixture that says too little.** `requires_consent` and `rows` were read with
`spec["…"]`, so an extra dataset omitting either raised `KeyError` out of
`/catalogue` — unauthenticated, and the first thing the portal calls. Defaulting
them would be worse than the crash: an absent `requires_consent` read as `False`
publishes a PII dataset as open.

**A fixture that says something different from governance.** The mock declared
`datasets.silver.meters_15m` keyed by subject DID in a column `sub`;
`governance.yaml` declares a `rec_registry` filter on `device_id`, and that is
what ds sends. Three vocabularies, no overlap, and nothing that could notice —
the dataset simply never returned a row, which is indistinguishable from a
subject who consented to nothing.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from dataset_api_mock.main import (
    DATASETS,
    REC_MEMBERS,
    REC_REGISTRY,
    _load_extra_datasets,
    _row_filter_spec,
)

GATED = "datasets.silver.meters_15m"
REPO = pathlib.Path(__file__).resolve().parents[3]
GOVERNANCE = REPO / "services" / "connector" / "governance" / "governance.yaml"
REC_FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "ds_e2e_rec.yaml"


# ── The fixture agrees with governance ────────────────────────────────────────


def _governance_row_filter(dataset: str) -> dict:
    doc = yaml.safe_load(GOVERNANCE.read_text())
    return doc["sources"][dataset]["row_filters"][0]


def test_the_gated_dataset_declares_the_filter_governance_declares():
    """Handler *and* column.

    ds builds the filter from `governance.yaml` and sends it here verbatim, so a
    fixture that names a different handler or a different column cannot be
    narrowed by any decision the platform is capable of producing.
    """
    declared = _row_filter_spec(DATASETS[GATED])
    expected = _governance_row_filter(GATED)
    assert declared["handler"] == expected["handler"] == REC_REGISTRY
    assert declared["args"]["column"] == expected["args"]["column"] == "device_id"


def test_the_gated_dataset_rows_carry_that_column():
    """A declaration the rows do not honour narrows to nothing just as silently."""
    column = _row_filter_spec(DATASETS[GATED])["args"]["column"]
    assert all(column in row for row in DATASETS[GATED]["rows"])


def test_no_row_is_keyed_by_a_subject_did():
    """The old vocabulary, pinned as gone.

    A DID in a payload column is also a privacy defect in its own right: it is
    derived from an unsalted email hash, so it re-identifies the subject to
    whoever later holds the rows. Rulebook `L-3`.
    """
    for name, spec in DATASETS.items():
        for row in spec.get("rows") or []:
            assert not any(
                isinstance(value, str) and value.startswith("did:")
                for value in row.values()
            ), f"{name} carries a DID in its payload"


def test_the_rec_fixture_matches_the_e2e_registry():
    """The mock and the real dataset-api must answer the same query the same way.

    They sit behind the same port depending on whether `fixtures/seed.sh` has
    run, and the members and sensors here are that file's. A drift between them
    makes a passing e2e run evidence about whichever backend happened to be up.
    """
    community = yaml.safe_load(REC_FIXTURE.read_text())["members"]
    for member in community.values():
        username = member["user_id"]
        assert username in REC_MEMBERS, f"{username} is in the e2e registry and not here"
        sensors = {
            asset["sensor_id"] for asset in member["assets"]["meter"].values()
        }
        assert set(REC_MEMBERS[username]["devices"]) == sensors


def test_the_unowned_device_belongs_to_nobody():
    """The negative control only controls if nothing claims it."""
    owned = {device for member in REC_MEMBERS.values() for device in member["devices"]}
    assert "ds-e2e-METER-9999" not in owned
    assert any(
        row["device_id"] == "ds-e2e-METER-9999" for row in DATASETS[GATED]["rows"]
    )


# ── A dataset must say enough to be served ────────────────────────────────────


def _extra(tmp_path, spec: dict) -> str:
    path = tmp_path / "extra.json"
    path.write_text(json.dumps({"datasets": {"datasets.bronze.thing": spec}}))
    return str(path)


def test_a_dataset_omitting_requires_consent_is_refused(tmp_path):
    """It is not defaulted, and `False` is the direction that leaks.

    A crash at startup is loud and happens once. A dataset silently published as
    open is quiet and happens on every request.
    """
    path = _extra(tmp_path, {"asset_id": "datasets.bronze.thing", "rows": []})
    with pytest.raises(RuntimeError, match="requires_consent"):
        _load_extra_datasets(path)


def test_a_dataset_omitting_rows_is_refused(tmp_path):
    """`len(spec["rows"])` was a `KeyError` out of `/catalogue`."""
    path = _extra(tmp_path, {"asset_id": "datasets.bronze.thing", "requires_consent": False})
    with pytest.raises(RuntimeError, match="rows"):
        _load_extra_datasets(path)


def test_a_dataset_omitting_its_asset_id_is_refused(tmp_path):
    """The asset id is what the agreement names, so a wrong one makes every
    verdict about some other dataset."""
    path = _extra(tmp_path, {"requires_consent": False, "rows": []})
    with pytest.raises(RuntimeError, match="asset_id"):
        _load_extra_datasets(path)


def test_a_consent_gated_dataset_without_a_row_filter_is_refused(tmp_path):
    """ds narrows these rows by one, so a dataset without one can only be served
    whole — which for a consent-gated dataset is the entire failure."""
    path = _extra(
        tmp_path,
        {"asset_id": "datasets.bronze.thing", "requires_consent": True, "rows": []},
    )
    with pytest.raises(RuntimeError, match="row filter"):
        _load_extra_datasets(path)


def test_an_external_dataset_needs_no_local_rows(tmp_path):
    """It names its upstream query instead — the one legitimate reason to omit
    `rows`, and the reason the check is not simply "every dataset has rows"."""
    path = _extra(
        tmp_path,
        {
            "asset_id": "datasets.bronze.thing",
            "requires_consent": False,
            "source": "external",
            "external_sql": "SELECT 1",
        },
    )
    assert "datasets.bronze.thing" in _load_extra_datasets(path)


def test_every_committed_dataset_passes_the_same_check():
    """The fixtures are held to what an extra dataset is held to."""
    for name, spec in DATASETS.items():
        assert spec.get("asset_id"), name
        assert "requires_consent" in spec, name
        if spec["requires_consent"]:
            assert _row_filter_spec(spec), name
