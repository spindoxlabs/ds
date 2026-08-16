"""`T-3` live — the reasoning that turns two documents into a verdict.

The property this flow asserts needs a running stack: two implementations of the
data plane, and a provider that has actually synced. What can be pinned without
one is the part that decides whether an observation counts — which spelling of
`dct:conformsTo` is the same declaration, what a 404 from a vocabulary means,
and the two ways this flow could report agreement where there is none.

Both of those are the failures worth guarding. A flow that compared nothing and
reported PASS would state agreement between one party and nothing, which is
exactly the condition the whole seam existed in for a release.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY
from ds_e2e.flows.semantic_model import SemanticModelFlow, _conforms_to, _is_node_form
from ds_e2e.http import HttpClient

IRI = "https://rec.dataspaces.localhost/ns/meter-readings"
ASSET = "datasets.silver.meters_15m"


@pytest.fixture
def settings() -> E2ESettings:
    return E2ESettings(_env_file=None)


def test_it_is_registered():
    """An unregistered flow is one that never runs."""
    assert FLOW_REGISTRY["semantic-model"] is SemanticModelFlow


# ── One declaration, three spellings ─────────────────────────────────────────


@pytest.mark.parametrize(
    "document",
    [
        {"dct:conformsTo": {"@id": IRI}},
        {"http://purl.org/dc/terms/conformsTo": {"@id": IRI}},
        {"properties": {"dct:conformsTo": {"@id": IRI}}},
        {"properties": {"conformsTo": IRI}},
    ],
    ids=["curie", "expanded", "in-properties", "bare-string"],
)
def test_the_same_declaration_is_read_through_every_spelling(document):
    """EDC compacts asset properties against the context the asset carried, and
    the connector declares `dct` only when something uses it. A reader that knew
    one spelling would report a missing model for a present one — a false
    failure at the exact boundary this flow exists to watch."""
    assert _conforms_to(document) == IRI


def test_a_document_declaring_nothing_reads_as_nothing():
    """Absent is a claim in its own right: it means *no model stated*, which is
    different from stating there is none."""
    assert _conforms_to({"properties": {"name": "meters"}}) is None


def test_a_literal_is_read_but_is_not_node_form():
    """Both halves matter. The value is legible, so the comparison can still
    run — and it is still wrong, because a bare string expands to a literal and
    a consumer following it gets text where a model should be. So it is reported
    rather than silently accepted or unparsed."""
    document = {"dct:conformsTo": IRI}
    assert _conforms_to(document) == IRI
    assert not _is_node_form(document)
    assert _is_node_form({"dct:conformsTo": {"@id": IRI}})


# ── The verdict ──────────────────────────────────────────────────────────────


def _flow(settings, *, assets, entry=None, single=None, vocabulary=None):
    """A flow wired to one provider and one data plane.

    `entry` is this plane's catalogue document for the asset — `None` means the
    plane does not hold it, which is the coverage case. It is served from both
    `GET /catalogue` (as a listing) and `GET /catalogue/{id}`, because the
    contract names both and the flow reads both; `single` overrides the
    single-entry answer alone, which is how a plane whose two routes disagree is
    expressed.

    `vocabulary` is `(status, media type, body)` — the media type is part of that
    route's contract and not of the catalogue's.
    """
    http = MagicMock(spec=HttpClient)
    http.bearer_headers.return_value = {}

    def _raw(method, url, **kwargs):
        if "/provider/assets" in url:
            return (200, assets)
        if url.endswith("/catalogue"):
            return (200, {"datasets": [entry] if entry else []})
        if "/catalogue/" in url and not url.endswith("/vocabulary"):
            return single or (200, entry)
        raise AssertionError(f"unexpected {method} {url}")

    def _document(url, **kwargs):
        if url.endswith("/vocabulary"):
            return vocabulary or (404, "application/json", None)
        raise AssertionError(f"unexpected document read {url}")

    http.get.return_value = {"status": "ok"}
    http.raw.side_effect = _raw
    http.get_document.side_effect = _document
    flow = SemanticModelFlow(settings, http)
    flow._check_health = lambda result: True  # the live half, not this test's subject
    # `M-8` resolution has its own reads and its own failure mode; the subject
    # here is the comparison between the two ends.
    flow._models_resolve_on_the_participant = lambda *a, **k: None
    flow._providers = lambda: (("rec", "http://rec.test"),)
    return flow


def _entry(iri=IRI, **overrides):
    """A data-plane catalogue entry, in the node-reference form both ends use."""
    doc = {"dct:identifier": ASSET, "dct:title": "meters"}
    if iri:
        doc["dct:conformsTo"] = {"@id": iri}
    doc.update(overrides)
    return doc


def _asset(**overrides):
    asset = {"@id": ASSET, "properties": {"dct:conformsTo": {"@id": IRI}}}
    asset.update(overrides)
    return asset


def _steps(result, name_contains):
    return [s for s in result.steps if name_contains in s.name]


def test_a_declaration_the_plane_contradicts_fails(settings, monkeypatch):
    """The defect the seam exists to make visible: a producer declaring one
    model and a renderer serving another. Before both ends existed, this was
    indistinguishable from agreement."""
    other = "https://saref.etsi.org/saref4ener/"
    flow = _flow(
        settings,
        assets=[_asset()],
        entry=_entry(other),
        vocabulary=(200, "application/ld+json", {"@context": {"a": 1}}),
    )
    result = flow.execute()
    failed = [s for s in _steps(result, "declaration matches") if s.status == "FAIL"]
    assert failed and other in failed[0].detail
    assert not result.passed


def test_agreement_passes_and_is_attributed_to_the_plane_that_answered(settings):
    """`E2E-13`: the step name carries the backend, because a green run against
    the mock and one against the real celine dataset-api are different evidence
    and used to be indistinguishable afterwards."""
    flow = _flow(
        settings,
        assets=[_asset()],
        entry=_entry(),
        vocabulary=(200, "application/ld+json", {"@context": {"kwh": {}}}),
    )
    result = flow.execute()
    assert result.passed
    assert any("dataset-api" in s.name for s in _steps(result, "declaration matches"))


def test_a_plane_stating_no_model_at_all_fails(settings):
    """Silence from the renderer does not confirm the declaration — it leaves it
    a claim nothing backs, which is the state this flow was written to end."""
    flow = _flow(
        settings,
        assets=[_asset()],
        entry=_entry(None),
        vocabulary=(200, "application/ld+json", {"@context": {}}),
    )
    result = flow.execute()
    assert not result.passed


def test_a_vocabulary_that_404s_under_a_declared_model_fails(settings):
    """404 means *no mapping*, and the catalogue entry has just stated one. The
    two answers contradict each other, and only their agreement is evidence."""
    flow = _flow(
        settings,
        assets=[_asset()],
        entry=_entry(),
        vocabulary=(404, "application/json", None),
    )
    result = flow.execute()
    failed = [s for s in _steps(result, "vocabulary is served") if s.status == "FAIL"]
    assert failed
    assert not result.passed


def test_a_vocabulary_served_as_plain_json_fails(settings):
    """A correct document under `application/json` is skipped by a consumer
    negotiating for linked data, so it is not found at all."""
    flow = _flow(
        settings,
        assets=[_asset()],
        entry=_entry(),
        vocabulary=(200, "application/json", {"@context": {"kwh": {}}}),
    )
    result = flow.execute()
    assert not result.passed


def test_declaring_nothing_anywhere_is_a_failure_not_a_quiet_pass(settings):
    """**The loud form of "not verified".**

    Zero declarations means zero comparisons, and a flow reporting PASS on that
    would state agreement between one party and nothing. `FlowResult.passed`
    already refuses an empty step list; this refuses a populated one that
    compared nothing."""
    flow = _flow(settings, assets=[{"@id": ASSET, "properties": {"name": "meters"}}])
    result = flow.execute()
    assert not result.passed
    assert any("exercises the semantic-model seam" in s.detail for s in result.steps)


def test_a_plane_holding_none_of_the_declared_datasets_fails_on_coverage(settings):
    """Inventory drift silently shrinking the comparison to nothing.

    Every remaining step would read PASS while the flow verified no agreement —
    the same shape as the case above, arriving by a different route. The datasets
    it could not compare are named, so the report says what was not checked."""
    flow = _flow(settings, assets=[_asset()])
    result = flow.execute()
    coverage = [s for s in _steps(result, "coverage") if s.status == "FAIL"]
    assert coverage
    assert coverage[0].data.get("absent") == [ASSET]
    assert not result.passed


def test_a_plane_whose_two_catalogue_routes_disagree_fails(settings):
    """`GET /catalogue` and `GET /catalogue/{id}` are both in the contract.

    Observed live rather than imagined: the real dataset-api registers an HTML
    view at `/catalogue/{id}` ahead of its JSON route, so resolving one dataset
    answers 500 while the listing is correct. The comparison runs off the
    listing, so a broken single-entry route cannot collapse coverage — and it is
    still reported, because a consumer resolving one dataset uses that route.
    """
    flow = _flow(
        settings,
        assets=[_asset()],
        entry=_entry(),
        single=(500, "Internal Server Error"),
        vocabulary=(200, "application/ld+json", {"@context": {"kwh": {}}}),
    )
    result = flow.execute()
    failed = [s for s in _steps(result, "single entry resolves") if s.status == "FAIL"]
    assert failed and "500" in failed[0].detail
    assert not result.passed
    # The model comparison still ran — that is the point of reading the listing.
    assert [s for s in _steps(result, "declaration matches") if s.status == "PASS"]
