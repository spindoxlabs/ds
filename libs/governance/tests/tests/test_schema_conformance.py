"""This repo's governance files must conform to the canonical schema.

`celine-utils/schema/governance.schema.json` is what every governance.yaml in
the ecosystem is written to. ds used to keep purpose and consent in its own
`policy:` block, which the schema tolerates (extra properties are allowed) but
nothing else reads — so a ds file and a producer-authored file describing the
same arrangement looked different and behaved differently.

Reading both shapes (§18) was half the fix. This is the other half: **ds's own
files are written in the canonical form**, and a test says so, because a
convention that lives only in a review comment drifts back within a release.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[4]

# A **cache** of https://celine-eu.github.io/schema/governance.schema.json —
# celine-utils is the only source of truth. Refresh with
# `task -d libs/governance schema:refresh`; see schema/README.md for why a copy
# exists at all (a test that needs the network enforces nothing when there is
# none).
SCHEMA = json.loads(
    (REPO / "schemas/governance.schema.json").read_text(encoding="utf-8")
)

GOVERNANCE_FILES = sorted(REPO.glob("services/*/governance/governance.yaml")) + sorted(
    REPO.glob("services/*/tests/fixtures/governance.yaml")
)


def test_governance_files_were_found():
    """A glob that matches nothing would make every test below vacuously pass."""
    assert GOVERNANCE_FILES, "no governance.yaml found — the glob is wrong"


@pytest.mark.parametrize("path", GOVERNANCE_FILES, ids=lambda p: p.name)
def test_conforms_to_the_canonical_schema(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors = sorted(
        Draft202012Validator(SCHEMA).iter_errors(doc), key=lambda e: list(e.path)
    )
    assert not errors, "\n".join(
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
    )


@pytest.mark.parametrize("path", GOVERNANCE_FILES, ids=lambda p: p.name)
def test_purpose_and_consent_live_where_the_schema_puts_them(path: Path):
    """Schema-valid is not enough — `policy:` passes as an extra property.

    The schema allows additional properties, so a file keeping purpose under
    `policy:` conforms and is still invisible to every other reader in the
    ecosystem. This asserts the placement the schema *defines*, which is the
    thing that actually has to match.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    blocks = list((doc.get("sources") or {}).items())
    blocks.append(("defaults", doc.get("defaults") or {}))

    offenders = [name for name, block in blocks if isinstance(block, dict) and "policy" in block]
    assert not offenders, (
        "these blocks still carry a ds-only `policy:` block; move `purpose` to "
        "`dataspace.purpose`, `consent.required` to `dataspace.consent_required` "
        f"and `obligations.contract_required` to `dataspace.contract_required`: {offenders}"
    )
