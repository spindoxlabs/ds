"""Generate the JSON Schemas ds publishes for the YAML shapes it defines.

**Generated, never hand-written.** The Pydantic models are the definition; a
schema maintained beside them drifts, and a schema that disagrees with the model
rejects valid files or accepts invalid ones with equal confidence.
`tests/tests/test_schema_export.py` regenerates and diffs, so drift fails CI
rather than surfacing as a producer's file being wrong about being wrong.

Scope is the shapes that **cross a repo boundary** — what a producer authoring a
file outside this repo needs in order to validate before ds ever sees it:

| File | Shape |
|---|---|
| ``sharing-offers.schema.json`` | ``sharing-offers.yaml`` |
| ``odrl-profile.schema.json``   | a deployer's ODRL profile |
| ``purpose-vocabulary.json``    | the slugs the *active* profile accepts |
| ``vocabularies.schema.json``   | the semantic vocabulary registry |

``governance.schema.json`` is not here: celine-utils defines that shape and this
repo only caches it. A schema lives where the shape is defined.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import OdrlProfile, load_odrl_profile
from .sharing import SharingOffer
from .vocabularies import Vocabulary

#: Where the published copies live, relative to the repo root.
SCHEMAS_DIRNAME = "schemas"

_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_BASE_URI = "https://spindoxlabs.github.io/ds/schemas"


def _titled(model: type, title: str, description: str) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema["title"] = title
    schema["description"] = description
    return schema


def sharing_offers_schema() -> dict[str, Any]:
    """Schema for a ``sharing-offers.yaml`` file.

    The file wraps the offers in a ``sharing_offers:`` key (see
    ``sharing._parse``), so the schema describes the *file*, not a bare offer —
    validating one offer would pass a file that declares them under the wrong key.
    """
    offer = _titled(
        SharingOffer,
        "Sharing offer",
        "A purpose-scoped bundle a person is asked to consent to.",
    )
    defs = offer.pop("$defs", {})
    defs["sharingOffer"] = offer
    return {
        "$schema": _DIALECT,
        "$id": f"{_BASE_URI}/sharing-offers.schema.json",
        "title": "ds sharing offers",
        "description": (
            "Sharing offers declared alongside a governance.yaml. Generated from "
            "the SharingOffer model in ds-governance — do not edit by hand."
        ),
        "type": "object",
        "required": ["sharing_offers"],
        "properties": {
            "sharing_offers": {
                "type": "array",
                "items": {"$ref": "#/$defs/sharingOffer"},
            }
        },
        "$defs": defs,
    }


def odrl_profile_schema() -> dict[str, Any]:
    """Schema for a deployer's ODRL profile YAML (``CONNECTOR_ODRL_PROFILE_PATH``)."""
    schema = _titled(
        OdrlProfile,
        "ds ODRL profile",
        (
            "The purpose taxonomy and ODRL namespace a deployment enforces "
            "against. Generated from the OdrlProfile model in ds-governance — "
            "do not edit by hand."
        ),
    )
    schema["$schema"] = _DIALECT
    schema["$id"] = f"{_BASE_URI}/odrl-profile.schema.json"
    return schema


def vocabularies_schema() -> dict[str, Any]:
    """Schema for a ``vocabularies.yaml`` file — the semantic vocabulary registry.

    Published for the same reason the others are: the file may be authored in a
    deployment repo, and a slug that is not a legal URL segment or a `format`
    other than `jsonld` should be caught there rather than at the connector's
    startup, which by design refuses to boot on it.
    """
    vocab = _titled(
        Vocabulary,
        "Vocabulary",
        "A semantic vocabulary this deployment publishes a local copy of.",
    )
    defs = vocab.pop("$defs", {})
    defs["vocabulary"] = vocab
    return {
        "$schema": _DIALECT,
        "$id": f"{_BASE_URI}/vocabularies.schema.json",
        "title": "ds vocabulary registry",
        "description": (
            "Semantic vocabularies served from /ns/{slug}, matched to a dataset "
            "by dcat.conforms_to. Generated from the Vocabulary model in "
            "ds-governance — do not edit by hand."
        ),
        "type": "object",
        "required": ["vocabularies"],
        "properties": {
            "vocabularies": {
                "type": "array",
                "items": {"$ref": "#/$defs/vocabulary"},
            }
        },
        "$defs": defs,
    }


def purpose_vocabulary(profile: OdrlProfile | None = None) -> dict[str, Any]:
    """The purpose slugs the active profile accepts, as a validatable enum.

    No static governance schema can carry this: the taxonomy is deployment
    configuration, so the permitted values are only knowable from the profile in
    force. A producer repo validates ``dataspace.purpose`` against this offline
    instead of discovering a typo when ds refuses the sync.

    ``/ns/policy`` serves the same taxonomy at runtime with its SKOS structure.
    Both are built from the profile, so they cannot disagree.
    """
    p = profile or load_odrl_profile()
    return {
        "$schema": _DIALECT,
        "$id": f"{_BASE_URI}/purpose-vocabulary.json",
        "title": "ds purpose vocabulary",
        "description": (
            "Purpose slugs accepted by the active ODRL profile. An entry in "
            "dataspace.purpose[] must be one of these, or an absolute IRI from "
            "another vocabulary. Regenerate whenever the profile changes."
        ),
        "namespace": p.namespace,
        "purposeBase": p.purpose_base,
        "purposes": [
            {
                "slug": c.slug,
                "label": c.label,
                "definition": c.definition,
                "broader": c.broader,
                "iri": p.purpose_iri(c.slug),
                "dpv": c.dpv_mapping.iri if c.dpv_mapping else None,
            }
            for c in p.purposes
        ],
        "enum": [c.slug for c in p.purposes],
    }


def generated_schemas() -> dict[str, dict[str, Any]]:
    """Filename → document, for every schema this repo generates."""
    return {
        "sharing-offers.schema.json": sharing_offers_schema(),
        "odrl-profile.schema.json": odrl_profile_schema(),
        "purpose-vocabulary.json": purpose_vocabulary(),
        "vocabularies.schema.json": vocabularies_schema(),
    }


def render(document: dict[str, Any]) -> str:
    """Stable on-disk form — sorted keys so a regeneration diff is meaningful."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_all(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name, document in generated_schemas().items():
        path = dest / name
        path.write_text(render(document), encoding="utf-8")
        written.append(path)
    return written
