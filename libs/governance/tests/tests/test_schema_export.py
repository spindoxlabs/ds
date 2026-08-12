"""The published schemas must match the models they were generated from.

A hand-edited schema beside a live model drifts, and both then look authoritative:
the schema rejects files the platform accepts, or accepts files it refuses. These
tests make the generated copies in `./schemas` a build artifact with a gate,
rather than a document someone remembers to update.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from ds.governance.models import load_odrl_profile
from ds.governance.schema_export import generated_schemas, purpose_vocabulary, render

REPO = Path(__file__).resolve().parents[4]
SCHEMAS = REPO / "schemas"


@pytest.mark.rule("M-9")
def test_schemas_directory_exists():
    """A wrong path would make every parametrised test below vacuous."""
    assert SCHEMAS.is_dir(), f"no schemas directory at {SCHEMAS}"


@pytest.mark.rule("M-9")
@pytest.mark.parametrize("name", sorted(generated_schemas()))
def test_published_copy_matches_regeneration(name: str):
    """Regenerating must produce no diff.

    If this fails, the model changed and the published schema did not — run
    `task -d libs/governance schema:generate` and commit the result.
    """
    published = (SCHEMAS / name).read_text(encoding="utf-8")
    assert published == render(generated_schemas()[name]), (
        f"{name} is stale — regenerate with `task -d libs/governance schema:generate`"
    )


@pytest.mark.rule("M-9")
@pytest.mark.parametrize("name", sorted(generated_schemas()))
def test_generated_schema_is_a_valid_schema(name: str):
    """A malformed schema silently validates nothing."""
    document = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    if name.endswith(".schema.json"):
        Draft202012Validator.check_schema(document)


def test_the_repos_own_sharing_offers_validate():
    """The shipped fixture must satisfy the schema ds publishes for it.

    Producers are told to validate against this. If our own worked example does
    not pass, the schema is wrong — nobody else's file is the right thing to
    debug first.
    """
    schema = json.loads((SCHEMAS / "sharing-offers.schema.json").read_text(encoding="utf-8"))
    offers = yaml.safe_load(
        (REPO / "services/connector/governance-rec/sharing-offers.yaml").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(offers)


def test_the_bundled_profile_validates_against_its_schema():
    schema = json.loads((SCHEMAS / "odrl-profile.schema.json").read_text(encoding="utf-8"))
    profile = yaml.safe_load(
        (REPO / "libs/governance/src/ds/governance/profiles/energy.yaml").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(profile)


@pytest.mark.rule("M-10")
def test_purpose_vocabulary_lists_exactly_the_active_profile():
    """The enum is the point — a stale one would pass a purpose sync refuses."""
    profile = load_odrl_profile()
    vocab = purpose_vocabulary(profile)
    assert vocab["enum"] == [c.slug for c in profile.purposes]
    assert set(vocab["enum"]) == set(profile.purpose_index)


@pytest.mark.rule("M-10")
def test_purpose_vocabulary_rejects_a_placeholder_term():
    """The regression this whole workstream came from."""
    vocab = json.loads((SCHEMAS / "purpose-vocabulary.json").read_text(encoding="utf-8"))
    for placeholder in ("energy-monitoring", "grid-resilience", "research", "analytics"):
        assert placeholder not in vocab["enum"]
