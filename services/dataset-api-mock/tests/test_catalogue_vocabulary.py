"""`GET /catalogue/{id}/vocabulary` — what the columns mean, from the plane that renders them.

The stand-in half of the semantic-model seam (`T-3`). Its contract-test half is
`libs/governance/tests/test_semantic_model_contract.py`, which pins the shape
both ends must agree on.

The real celine `dataset-api` implements this route by deriving a JSON-LD
context from the dataset's mapping spec; this mock must answer the same shape, or
an e2e run against the default stack exercises a contract only the other backend
has.

**Why the mock needs it at all**, given its defects are excluded from assessment:
the two backends share port 30002 and a run does not say which answered. A seam
implemented on one and 404 on the other makes a green suite evidence about
whichever happened to be up — the failure `test_the_rec_fixture_matches_the_e2e_registry`
already guards for row filters, arriving at a second surface.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient

from dataset_api_mock import main

GATED = "datasets.silver.meters_15m"
UNMAPPED = "datasets.gold.om_weather_features"
REPO = pathlib.Path(__file__).resolve().parents[3]
GOVERNANCE = REPO / "services" / "connector" / "governance-rec" / "governance.yaml"
DEFINITION = REPO / "services" / "connector" / "governance-rec" / "meter-readings.jsonld"


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def _vocabulary(client: TestClient, dataset: str):
    return client.get(f"/catalogue/{dataset}/vocabulary")


# ── The shape both planes must serve ──────────────────────────────────────────


def test_it_is_served_as_json_ld_not_json(client: TestClient):
    """`application/ld+json`, explicitly.

    A consumer content-negotiating for JSON-LD skips `application/json`, so a
    correct document under the wrong media type is not found at all.
    """
    res = _vocabulary(client, GATED)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/ld+json")


def test_the_context_is_keyed_by_the_columns_query_returns(client: TestClient):
    """Source columns, not ontology terms.

    The context exists to be applied to a row unchanged. Keyed by target term it
    would describe a document this plane never emits — and `device_id` maps to
    `deviceId`, so the two keyings are observably different here rather than
    coincidentally equal.
    """
    context = _vocabulary(client, GATED).json()["@context"]
    columns = {column for row in main.DATASETS[GATED]["rows"] for column in row}
    assert columns <= set(context)


def test_a_term_is_a_node_reference_carrying_its_datatype(client: TestClient):
    context = _vocabulary(client, GATED).json()["@context"]
    assert context["device_id"] == {
        "@id": "https://rec.dataspaces.localhost/ns/meter-readings#deviceId",
        "@type": "xsd:string",
    }
    assert context["kwh"]["@type"] == "xsd:decimal"


def test_every_prefix_the_document_uses_is_declared(client: TestClient):
    """An unexpandable CURIE is not a smaller failure than a missing term.

    It is the same failure, found by the consumer instead of here — so `xsd`,
    used by every datatype, and `dct`, used by `conformsTo`, are both in the
    context rather than assumed.
    """
    context = _vocabulary(client, GATED).json()["@context"]
    used = {
        value.partition(":")[0]
        for term in context.values()
        if isinstance(term, dict)
        for value in (term.get("@type"),)
        if value and "://" not in value
    }
    assert used <= {prefix for prefix, iri in context.items() if isinstance(iri, str)}


def test_the_model_it_states_is_the_one_the_catalogue_advertises(client: TestClient):
    """Identity and locator, agreeing.

    The route is where this participant *serves* the model; `dct:conformsTo` is
    what the model *is*. Both read one field, so a dataset cannot advertise one
    model in the catalogue and another in its vocabulary.
    """
    doc = _vocabulary(client, GATED).json()
    entry = client.get(f"/catalogue/{GATED}").json()
    assert doc["dct:conformsTo"] == entry["dct:conformsTo"]


def test_it_states_the_model_governance_declares(client: TestClient):
    """The reconciliation the seam is for, at fixture level.

    `governance.yaml` is the producer's declaration and ds publishes it into the
    DSP catalogue; this is what the plane rendering the rows says. Two holders of
    one fact — and a producer that could declare one model and serve another is
    exactly the unfalsifiable claim `T-3` exists to close.
    """
    declared = yaml.safe_load(GOVERNANCE.read_text())["sources"][GATED]["dcat"]["conforms_to"]
    assert _vocabulary(client, GATED).json()["dct:conformsTo"] == {"@id": declared}


def test_every_mapped_term_exists_in_the_definition_this_participant_serves(
    client: TestClient,
):
    """A mapping may only use terms the declared model actually defines.

    The REC serves `meter-readings.jsonld` at `GET /ns/meter-readings`, so a
    mapping naming `#power` would publish a context pointing into its own
    namespace at something nothing defines — an address this participant
    answers at, for a term it does not hold.
    """
    defined = {
        term["@id"]
        for term in json.loads(DEFINITION.read_text())["@context"].values()
        if isinstance(term, dict) and "@id" in term
    }
    mapped = {term["@id"] for term in _vocabulary(client, GATED).json()["@context"].values() if isinstance(term, dict)}
    assert mapped <= defined, f"mapped terms the definition does not declare: {mapped - defined}"


# ── What 404 means, and what it does not ──────────────────────────────────────


def test_a_dataset_with_no_mapping_is_404_and_declares_no_model_either(client: TestClient):
    """404 is *"no mapping here"*, and the catalogue must not contradict it.

    The two answers are different claims and only their agreement is meaningful:
    a dataset 404ing here while advertising `dct:conformsTo` would be declaring
    a model it cannot describe.
    """
    assert _vocabulary(client, UNMAPPED).status_code == 404
    assert "dct:conformsTo" not in client.get(f"/catalogue/{UNMAPPED}").json()


def test_an_unknown_dataset_is_404(client: TestClient):
    assert _vocabulary(client, "datasets.gold.nope").status_code == 404


def test_the_greedy_sibling_route_does_not_swallow_this_one(client: TestClient):
    """The trap this route is one declaration order away from falling into.

    `/catalogue/{asset_id:path}` matches greedily, so declared after it this path
    resolves to an asset named `…/vocabulary` and answers 404 — the one wrong
    answer available, because 404 already means "declares no model". Asserted by
    the *content*: a 200 here cannot come from the sibling.
    """
    res = _vocabulary(client, GATED)
    assert res.status_code == 200
    assert "@context" in res.json()


def test_it_needs_no_credentials(client: TestClient):
    """A consumer decides whether it can use a dataset before it negotiates for
    one, so gating the vocabulary would gate discovery. It describes the shape of
    the data, never the data."""
    res = TestClient(main.app).get(f"/catalogue/{GATED}/vocabulary")
    assert res.status_code == 200


# ── A mapping that would 500 the route is refused at load ─────────────────────


def _extra(tmp_path, ontology) -> str:
    path = tmp_path / "extra.json"
    path.write_text(
        json.dumps(
            {
                "datasets": {
                    "datasets.bronze.thing": {
                        "asset_id": "datasets.bronze.thing",
                        "requires_consent": False,
                        "rows": [],
                        "ontology": ontology,
                    }
                }
            }
        )
    )
    return str(path)


@pytest.mark.parametrize(
    "ontology",
    [
        {"fields": []},
        {"target_type": "x"},
        {"fields": [{"source": "kwh"}]},
        {"fields": [{"target": "x:kwh"}]},
    ],
    ids=["no-fields", "no-fields-key", "no-target", "no-source"],
)
def test_a_mapping_that_could_not_be_served_is_refused_at_load(tmp_path, ontology):
    """A crash at startup is loud and happens once; a 500 from an unauthenticated
    route is quiet and happens on every request. The same argument the fixture
    validation already makes for `rows` and `requires_consent`."""
    with pytest.raises(RuntimeError, match="ontology|mapping"):
        main._load_extra_datasets(_extra(tmp_path, ontology))


def test_a_dataset_may_still_declare_no_mapping_at_all(tmp_path):
    """Optional, and its absence is a claim — *no model stated*."""
    path = tmp_path / "extra.json"
    path.write_text(
        json.dumps(
            {
                "datasets": {
                    "datasets.bronze.thing": {
                        "asset_id": "datasets.bronze.thing",
                        "requires_consent": False,
                        "rows": [],
                    }
                }
            }
        )
    )
    assert main._load_extra_datasets(str(path))


# ── The second producer ───────────────────────────────────────────────────────


def test_the_other_producer_serves_its_own_model(client: TestClient):
    """Two participants, two models, one route. `conforms_to` is per dataset and
    per producer — a platform-wide vocabulary is the thing this must not
    become."""
    doc = _vocabulary(client, "datasets.gold.grid_capacity").json()
    assert doc["dct:conformsTo"] == {"@id": "https://grid-operator.dataspaces.localhost/ns/grid-capacity"}
    assert doc["@context"]["headroom_kw"]["@id"].endswith("#headroomKw")
