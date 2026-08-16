"""The declared payload model and the rendered one, as both ends must read it.

`T-3`, and the assertion the whole semantic-model seam exists for. A dataset
declares `dcat.conforms_to` in `governance.yaml`; ds validates it, emits
`dct:conformsTo` into the DSP catalogue and serves a local copy at `/ns/{slug}`.
None of that establishes that the rows a consumer receives mean what the IRI
says. **Two holders of one fact, and until both existed nothing could compare
them** — a producer could declare any model and return anything.

The other holder is the data plane. The real one is the celine `dataset-api`,
out of this repository; its expected interface is fixed in
`.agents/plans/semantic-model-seam.md`:

    GET /catalogue/{id}            → `dct:conformsTo` = the model's canonical IRI
    GET /catalogue/{id}/vocabulary → 200 JSON-LD, or 302 to where it is published

These are **contract tests, not integration tests**. They pin the shape both ends
must agree on, so the ds side can be written and reviewed while the data-plane
side is still being built — which is the situation this seam is actually in.
Whether a *running* data plane honours it is `E2E-16`, and belongs to `ds-e2e`.

The failure this guards is the one that already happened once at this boundary:
the connector emitted `{handler, args, principals}`, the PEP read
`{column, subject_ids}`, and every allow-with-a-filter died as a `KeyError`
(`test_dataplane_contract.py`). An unstated contract between two repositories is
discovered in production.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ds.governance.vocabularies import load_vocabularies

CANONICAL = "https://w3id.org/celine-eu#"

ROOT = Path(__file__).resolve().parents[3]
PRODUCERS = sorted(ROOT.glob("services/connector/governance-*/governance.yaml"))


def _datasets(governance: Path) -> dict:
    """`sources`, not `datasets` — the key names where a dataset *comes from*.

    Worth stating because the obvious guess is wrong and fails open: a reader
    looking up `datasets` gets `{}`, and every assertion below then passes over
    an empty mapping.
    """
    raw = yaml.safe_load(governance.read_text(encoding="utf-8")) or {}
    return raw.get("sources") or {}


def _declared_models(governance: Path) -> dict[str, str]:
    """`{dataset id: conforms_to}` for every dataset that declares one."""
    return {
        name: (spec.get("dcat") or {}).get("conforms_to")
        for name, spec in _datasets(governance).items()
        if (spec.get("dcat") or {}).get("conforms_to")
    }


# ── The producers this repository ships ───────────────────────────


def test_there_are_producers_to_check():
    """Guard the guard: a glob that matched nothing would pass everything."""
    assert len(PRODUCERS) >= 2, (
        f"only {len(PRODUCERS)} producer governance files found under "
        "services/connector/ — the glob is probably broken"
    )


@pytest.mark.rule("M-4")
@pytest.mark.parametrize("governance", PRODUCERS, ids=lambda p: p.parent.name)
def test_at_least_one_dataset_declares_its_payload_model(governance: Path):
    """`M-6` means ds mandates no model — it does not mean no fixture uses the
    seam. A seam nothing exercises is a seam nobody notices breaking, and this
    one shipped unused: `conforms_to` appeared in no governance file and both
    registries were empty."""
    assert _declared_models(governance), (
        f"{governance.parent.name} declares no `dcat.conforms_to` on any dataset, "
        "so nothing exercises the semantic-model seam for this producer"
    )


@pytest.mark.rule("M-4", "M-8")
@pytest.mark.parametrize("governance", PRODUCERS, ids=lambda p: p.parent.name)
def test_every_declared_model_is_served_by_this_participant(governance: Path):
    """A declared IRI a consumer cannot dereference is what `M-7` is about.

    An unregistered IRI is a *warning* at sync, deliberately — an external
    standard is a legitimate reference without a local mirror (`V-6`). But a
    producer that declares an IRI **in its own namespace** and does not serve it
    is not referencing somebody else's standard; it is publishing an address it
    does not answer at.
    """
    registry = load_vocabularies(governance.parent / "vocabularies.yaml")
    served = {v.iri for v in registry.vocabularies}
    host = governance.parent.name.removeprefix("governance-")

    for dataset, iri in _declared_models(governance).items():
        if host not in iri:
            continue  # somebody else's standard; V-6 says that is fine unmirrored
        assert iri in served, (
            f"{dataset} declares {iri}, which is this participant's own namespace, "
            f"and {governance.parent.name}/vocabularies.yaml does not serve it. "
            f"Register it, or point conforms_to at a model somebody else publishes."
        )


@pytest.mark.rule("M-8")
@pytest.mark.parametrize("governance", PRODUCERS, ids=lambda p: p.parent.name)
def test_a_participants_own_vocabulary_needs_no_network(governance: Path):
    """`V-5` at deployment scale.

    The registries shipped empty so that `task start` reached no network, and a
    registered entry with a `source:` reintroduces exactly that dependency —
    startup fetches and **fails closed** if it cannot (`V-4`). An entry the
    participant publishes itself must therefore ship its definition, or a cold
    boot of the dev stack depends on a third party being up.
    """
    registry = load_vocabularies(governance.parent / "vocabularies.yaml")
    host = governance.parent.name.removeprefix("governance-")

    for vocab in registry.vocabularies:
        if host not in vocab.iri:
            continue
        assert vocab.definition, (
            f"{vocab.slug} is this participant's own vocabulary but is fetched "
            f"from {vocab.source!r}. Ship it with `definition:` instead — a cold "
            f"`task start` must not depend on an external host."
        )


# ── The shape ds publishes, which the data plane must match ───────
#
# Asserted against ds's real emitters, not against a hand-built dict. A test that
# constructs the value it then checks proves nothing about the code — the shape
# the data plane has to agree with is whatever `to_dcat_dataset` and the EDC
# mapper actually emit, so that is what these read.


def _rule_with(conforms_to: str | None):
    from ds.governance.models import GovernanceRuleV2

    raw = {
        "title": "Meter readings",
        "dataspace": {
            "expose": True,
            "asset": {"id": "datasets.silver.meters_15m"},
            "data_address": {"type": "HttpData", "base_url": "http://dataset-api/query"},
        },
    }
    if conforms_to:
        raw["dcat"] = {"conforms_to": conforms_to}
    return GovernanceRuleV2.model_validate(raw)


def _evidence(key: str, rule):
    from ds.governance.compliance.evidence import DatasetEvidence

    return DatasetEvidence(
        key=key,
        rule=rule,
        asset_id=key,
        policy_id=f"{key}-policy",
        contract_id=f"{key}-contract",
    )


@pytest.mark.rule("M-4")
def test_ds_publishes_the_model_as_a_node_reference_not_a_string():
    """`{"@id": …}`, not a bare string.

    `dct:conformsTo` points at a *resource*. A bare string expands to a literal
    in JSON-LD, so a consumer following it gets a piece of text rather than a
    model. The data plane's catalogue entry has to use the same form, or the two
    halves of one catalogue disagree about what the property means.
    """
    from ds.governance.compliance.evidence import to_dcat_dataset

    rule = _rule_with(CANONICAL)
    dataset = to_dcat_dataset(
        _evidence("datasets.silver.meters_15m", rule),
        offer={},
        base_url="https://rec.dataspaces.localhost",
        publisher_id="rec",
    )

    assert dataset["dct:conformsTo"] == {"@id": CANONICAL}


@pytest.mark.rule("M-4")
def test_ds_omits_the_model_rather_than_nulling_it_when_undeclared():
    """A dataset that states no model and a dataset that states "no model" are
    different claims, and only the first is what silence means. A `null` would
    make an undeclared dataset indistinguishable from one asserting it conforms
    to nothing — so the data plane omits the key too."""
    from ds.governance.compliance.evidence import to_dcat_dataset

    dataset = to_dcat_dataset(
        _evidence("datasets.silver.meters_15m", _rule_with(None)),
        offer={},
        base_url="https://rec.dataspaces.localhost",
        publisher_id="rec",
    )

    assert "dct:conformsTo" not in dataset


@pytest.mark.rule("M-4")
def test_the_model_and_the_protocol_stay_on_different_nodes():
    """Two `dct:conformsTo` claims exist and they answer different questions.

    The one on a **distribution** names the protocol — how you fetch it. The one
    on the **dataset** names the semantic model — what the columns mean. Merged
    onto one node they become indistinguishable to a reader, and a consumer
    checking "can I parse this" would read the DSP IRI as the payload model.
    """
    from ds.governance.compliance.evidence import to_dcat_dataset

    dataset = to_dcat_dataset(
        _evidence("datasets.silver.meters_15m", _rule_with(CANONICAL)),
        offer={},
        base_url="https://rec.dataspaces.localhost",
        publisher_id="rec",
    )

    assert dataset["dct:conformsTo"] == {"@id": CANONICAL}
    distribution = dataset["dcat:distribution"][0]
    assert distribution["dct:conformsTo"] != dataset["dct:conformsTo"]


@pytest.mark.rule("M-4", "M-7")
def test_the_declaration_is_the_canonical_iri_and_is_shared_across_datasets():
    """The correction that matters most in this design.

    Making the per-dataset vocabulary route the value of `conforms_to` conflates
    identifier with locator: two datasets conforming to one profile would look
    like two different models to a consumer, which is what a shared ontology
    exists to prevent. Here they are declared separately and must come out equal.
    """
    from ds.governance.compliance.evidence import to_dcat_dataset

    emitted = [
        to_dcat_dataset(
            _evidence(key, _rule_with(CANONICAL)),
            offer={},
            base_url="https://rec.dataspaces.localhost",
            publisher_id="rec",
        )["dct:conformsTo"]
        for key in ("datasets.silver.meters_15m", "datasets.gold.grid_capacity")
    ]

    assert emitted[0] == emitted[1] == {"@id": CANONICAL}
