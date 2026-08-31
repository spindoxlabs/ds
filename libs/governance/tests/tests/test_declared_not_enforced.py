"""GOV-12, GOV-13, GOV-14 · ids that identify, and declarations that are honest.

Three rows, one theme: governance says something and the platform does not act
on it, or acts on it under a name that no longer picks it out.

The rule these settle on, and it is the same one `GOV-04` established from the
other side: **the platform must not appear to do something it does not do** —
outward to a counterparty (`DSSC-AUP-06`) and inward to the producer who wrote
the file. Deleting an unimplemented field would satisfy that by silence; the
next producer re-adds the key expecting it to work. Reporting it says what is
true.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ds.governance.compliance.checks import UNENFORCED_DECLARATIONS
from ds.governance.mapper import GovernanceMapper
from ds.governance.models import (
    DataspaceContract,
    DataspacePolicy,
    DataspaceSpec,
    GovernanceRuleV2,
    PolicyObligations,
)

from .test_compliance_checks import exposed_dataset, run, write_governance

BASE_URL = "https://rec.dataspaces.localhost"


def _mapper() -> GovernanceMapper:
    return GovernanceMapper(participant_id="provider", base_url=BASE_URL)


# ── GOV-12 · a policy id and a contract id are different things ──────────────


def test_policy_and_contract_ids_differ_by_default():
    mapper = _mapper()
    rule = GovernanceRuleV2(access_level="open", classification="green")
    policy = mapper.to_policy_create("datasets.gold.meters", rule)
    contract = mapper.to_contract_definition(
        "datasets.gold.meters", rule, policy["@id"], "asset-1"
    )
    assert policy["@id"] != contract["@id"]
    assert policy["@id"].endswith("-policy")
    assert contract["@id"].endswith("-contract")


def test_naming_the_access_policy_no_longer_renames_the_contract():
    """The counterfactual.

    `to_contract_definition` derived its `@id` from `access_policy_id`, so a
    deployment that named its access policy gave the contract definition the
    same id. Nothing 409s — they are separate EDC collections — the id simply
    stops saying which entity is meant.
    """
    mapper = _mapper()
    rule = GovernanceRuleV2(
        access_level="open",
        classification="green",
        dataspace=DataspaceSpec(
            expose=True,
            contract=DataspaceContract(access_policy_id="meters-access"),
        ),
    )
    policy = mapper.to_policy_create("datasets.gold.meters", rule)
    contract = mapper.to_contract_definition(
        "datasets.gold.meters", rule, policy["@id"], "asset-1"
    )
    assert policy["@id"] == "meters-access"
    assert contract["@id"] == "datasets-gold-meters-contract"


def test_the_contract_definition_id_can_still_be_named():
    mapper = _mapper()
    rule = GovernanceRuleV2(
        access_level="open",
        classification="green",
        dataspace=DataspaceSpec(
            expose=True,
            contract=DataspaceContract(
                access_policy_id="meters-access",
                contract_definition_id="meters-offer",
            ),
        ),
    )
    contract = mapper.to_contract_definition(
        "datasets.gold.meters", rule, "meters-access", "asset-1"
    )
    assert contract["@id"] == "meters-offer"


@pytest.mark.rule("A-5")
def test_a_collision_reintroduced_by_configuration_fails_the_gate(tmp_path: Path):
    """The check the row asked for: configuration can still collide them.

    `contract_definition_id` is an override, so a deployment can set it equal to
    the policy id by hand. That is now a validation error rather than a thing
    somebody notices in a log six months later.
    """
    write_governance(
        tmp_path,
        {
            "sources": {
                "a": {
                    **exposed_dataset(),
                    "dataspace": {
                        "expose": True,
                        "contract": {
                            "access_policy_id": "same-id",
                            "contract_definition_id": "same-id",
                        },
                    },
                }
            }
        },
    )
    result = run(tmp_path / "governance.yaml")
    assert not result.passed
    assert any(
        e["check"] == "policy-contract-id-collision" for e in result.asdict()["errors"]
    )


# ── GOV-13, GOV-14 · declared and not enforced ───────────────────────────────


@pytest.mark.parametrize(
    "label,dotted,_c", UNENFORCED_DECLARATIONS, ids=lambda v: str(v)[:40]
)
def test_every_unenforced_field_is_still_unenforced(label, dotted, _c):
    """A guard on the list itself.

    If one of these is wired to an emitter or an enforcement point, its line here
    must go — otherwise the warning tells a producer their setting does nothing
    while it quietly starts working. Wiring one and leaving the row is the
    inverse of the defect, and just as confusing.
    """
    mapper = _mapper()
    rule = GovernanceRuleV2(
        access_level="open",
        classification="green",
        policy=DataspacePolicy(
            obligations=PolicyObligations(
                notify_on_access=True, anonymize_before_use=True
            ),
        ),
    )
    offer = mapper.to_odrl_offer("datasets.gold.meters", rule)
    rendered = str(offer)
    leaf = dotted.rsplit(".", 1)[-1]
    assert leaf not in rendered, (
        f"{label} now reaches the emitted offer — remove it from "
        "UNENFORCED_DECLARATIONS in the same change"
    )


def test_a_validity_window_is_reported_rather_than_silently_ignored(tmp_path: Path):
    """`GOV-13`. The dates were parsed, order-checked, and read by nothing —
    so an offer declared valid until a date simply did not expire."""
    write_governance(
        tmp_path,
        {
            "sources": {
                "a": {
                    **exposed_dataset(),
                    "policy": {
                        "purpose": ["GridMonitoring"],
                        "valid_from": "2026-01-01",
                        "valid_until": "2026-12-31",
                    },
                }
            }
        },
    )
    result = run(tmp_path / "governance.yaml")
    warnings = [
        w for w in result.asdict()["warnings"] if w["check"] == "declared-not-enforced"
    ]
    assert {w["message"].split(" is declared")[0] for w in warnings} == {
        "policy.valid_from",
        "policy.valid_until",
    }
    assert result.passed, "an unimplemented platform feature is not an invalid file"


def test_unenforced_obligations_are_reported(tmp_path: Path):
    """`GOV-14`. `anonymize_before_use` is the one that matters: a producer who
    sets it believes the data plane anonymises, and it returns the rows the row
    filter selects, unchanged."""
    write_governance(
        tmp_path,
        {
            "sources": {
                "a": {
                    **exposed_dataset(),
                    "policy": {
                        "purpose": ["GridMonitoring"],
                        "obligations": {
                            "notify_on_access": True,
                            "anonymize_before_use": True,
                        },
                    },
                }
            }
        },
    )
    result = run(tmp_path / "governance.yaml")
    messages = " ".join(
        w["message"]
        for w in result.asdict()["warnings"]
        if w["check"] == "declared-not-enforced"
    )
    assert "notify_on_access" in messages
    assert "anonymize_before_use" in messages
    assert "unchanged" in messages


def test_a_file_declaring_none_of_them_is_quiet(tmp_path: Path):
    """Or the warning appears on every dataset and stops being read."""
    write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
    result = run(tmp_path / "governance.yaml")
    assert not [
        w for w in result.asdict()["warnings"] if w["check"] == "declared-not-enforced"
    ]


# ── GOV-14 · the one that could be wired, and was ────────────────────────────


def test_documentation_url_reaches_the_published_asset():
    """Description, not policy — so publishing it claims nothing about
    enforcement, which is why this one is emitted and the obligations are not."""
    mapper = _mapper()
    rule = GovernanceRuleV2(
        access_level="open",
        classification="green",
        documentation_url="https://docs.example.test/meters",
    )
    asset = mapper.to_asset_create("datasets.gold.meters", rule)
    assert asset["properties"]["dct:references"] == "https://docs.example.test/meters"
    assert asset["@context"]["dct"] == "http://purl.org/dc/terms/"


def test_dct_is_not_declared_when_nothing_uses_it():
    mapper = _mapper()
    rule = GovernanceRuleV2(access_level="open", classification="green")
    asset = mapper.to_asset_create("datasets.gold.meters", rule)
    assert "dct" not in asset["@context"]


# ── GOV-07 · DCAT-AP conformance, rulebook C-12 / DSSC-DSO-11 ────────────────


@pytest.mark.rule("C-12", "C-14")
def test_a_dataset_missing_a_mandatory_dcat_property_fails(tmp_path: Path):
    """The gap the rulebook recorded: `validate` checked internal coherence and
    referential integrity, and never the standard the catalogue is judged as.

    Both mandatory properties have a fallback in the emitter — the dataset key
    for `dct:title`, `""` for `dct:description` — so the published record is
    structurally valid and empty. A validator that inspected the *output* would
    pass it; this one checks the input that produced it.
    """
    write_governance(
        tmp_path,
        {
            "sources": {
                "a": {
                    "access_level": "open",
                    "policy": {"purpose": ["GridMonitoring"]},
                    "dataspace": {
                        "expose": True,
                        "data_address": {"base_url": "http://dataset-api:30002"},
                    },
                }
            }
        },
    )
    result = run(tmp_path / "governance.yaml")
    errors = [e for e in result.asdict()["errors"] if e["check"] == "dcat-ap"]
    assert {e["message"].split(" is mandatory")[0] for e in errors} == {
        "dct:title",
        "dct:description",
    }
    assert not result.passed


@pytest.mark.rule("C-12", "C-14")
def test_a_complete_dataset_raises_no_dcat_ap_error(tmp_path: Path):
    write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
    result = run(tmp_path / "governance.yaml")
    assert not [e for e in result.asdict()["errors"] if e["check"] == "dcat-ap"]


def test_recommended_properties_only_warn(tmp_path: Path):
    """DCAT-AP's own distinction, not a severity we chose. A missing licence is
    worth saying and is not a reason to refuse the import."""
    write_governance(tmp_path, {"sources": {"a": exposed_dataset()}})
    result = run(tmp_path / "governance.yaml")
    warnings = [w for w in result.asdict()["warnings"] if w["check"] == "dcat-ap"]
    assert any("dct:license" in w["message"] for w in warnings)
    assert result.passed


def test_the_repositorys_own_governance_files_conform(tmp_path: Path):
    """The check is worth nothing if the platform's own fixtures fail it.

    Same argument `test_the_repos_own_sharing_offers_validate` makes: producers
    are told to validate against this, so our worked examples must pass.
    """
    repo = Path(__file__).resolve().parents[4]
    files = sorted(repo.glob("services/connector/governance-*/governance.yaml"))
    assert files, "no governance fixtures found — this test would be vacuous"
    for path in files:
        result = run(path)
        dcat_errors = [e for e in result.asdict()["errors"] if e["check"] == "dcat-ap"]
        assert not dcat_errors, f"{path.name}: {dcat_errors}"


# ── GOV-08 · a policy version a consumer can ask about ───────────────────────


def test_no_version_is_emitted_when_the_profile_declares_none():
    """Naming a version the profile does not have would be worse than silence."""
    from ds.governance.models import OdrlProfile

    mapper = GovernanceMapper(
        participant_id="provider", base_url=BASE_URL, profile=OdrlProfile()
    )
    rule = GovernanceRuleV2(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("datasets.gold.meters", rule)
    assert not [k for k in offer if k.endswith(":profileVersion")]


def test_the_profile_version_reaches_the_offer():
    """`GOV-08`, the smallest concrete piece of the rulebook's metadata-versioning
    item: a consumer holding an agreement can ask what the terms meant when they
    negotiated."""
    from ds.governance.models import OdrlProfile

    profile = OdrlProfile(version="2026-08")
    mapper = GovernanceMapper(
        participant_id="provider", base_url=BASE_URL, profile=profile
    )
    rule = GovernanceRuleV2(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("datasets.gold.meters", rule)
    assert offer[f"{profile.prefix}:profileVersion"] == "2026-08"


def test_the_version_is_metadata_and_not_a_constraint():
    """The distinction `GOV-04` and `GOV-10` both turn on: a term inside a
    permission is evaluated by a policy engine, and this one must not be — no
    binding exists for it, and an unenforced constraint is what DSSC-AUP-06
    forbids."""
    from ds.governance.models import OdrlProfile

    mapper = GovernanceMapper(
        participant_id="provider",
        base_url=BASE_URL,
        profile=OdrlProfile(version="2026-08"),
    )
    rule = GovernanceRuleV2(access_level="open", classification="green")
    offer = mapper.to_odrl_offer("datasets.gold.meters", rule)
    for permission in offer["odrl:permission"]:
        for constraint in permission.get("odrl:constraint", []):
            assert "profileVersion" not in str(constraint)
