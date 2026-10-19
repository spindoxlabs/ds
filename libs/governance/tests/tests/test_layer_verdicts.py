"""`allow_all` / `deny_all` — a layer's verdict, not a filter (celine-utils `LAYER_HANDLERS`).

The two-layer row policy gives every exposed dataset a `person` and an `organization`
layer; a layer that narrows nothing states it with `allow_all`, one that admits no row
with `deny_all`, and `binds` names the layer. Neither names a column, neither is
per-subject access control, so neither is a consent signal — and until ds knew them,
the resolver dropped both whenever they sat on the person layer (no `args`), which is
the only reason an organization-bound dataset's `allow_all` did not gate it, and the
reason a person-layer `deny_all` would have served.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ds.governance.consent import consent_gate, narrows_person
from ds.governance.mapper import GovernanceMapper
from ds.governance.models import GovernanceRuleV2, OdrlProfile, RowFilter
from ds.governance.resolver import GovernanceResolver

from .test_compliance_checks import codes, exposed_dataset, run, write_governance

PERSON_ALLOW = {"handler": "allow_all", "binds": "person"}
PERSON_DENY = {"handler": "deny_all", "binds": "person"}
ORGANIZATION_ALLOW = {"handler": "allow_all", "binds": "organization"}
ORGANIZATION = {
    "handler": "organization_match",
    "binds": "organization",
    "args": {"column": "dso_id"},
}
PERSON = {"handler": "rec_registry", "args": {"column": "device_id"}}


def _rule(*filters: dict, **extra) -> GovernanceRuleV2:
    return GovernanceRuleV2.model_validate({"row_filters": list(filters), **extra})


def _load(tmp_path: Path, *filters: dict) -> GovernanceRuleV2:
    path = write_governance(
        tmp_path, {"sources": {"a": {"row_filters": list(filters)}}}
    )
    return GovernanceResolver.from_file(path).resolve("a")


# ── the model ────────────────────────────────────────────────────


def test_a_person_layer_verdict_names_no_column():
    for verdict in (PERSON_ALLOW, PERSON_DENY):
        row_filter = RowFilter.model_validate(verdict)
        assert row_filter.is_layer_verdict
        assert row_filter.binds_person and not row_filter.narrows_person


def test_a_person_filter_still_names_its_column():
    with pytest.raises(ValidationError, match="names no args.column"):
        RowFilter.model_validate({"handler": "rec_registry"})


def test_a_verdict_without_binds_is_refused():
    """Upstream's rule, reached through ds's subclass: only `binds` says which layer."""
    with pytest.raises(ValidationError, match="must state binds"):
        _rule({"handler": "deny_all"})


# ── the consent gate (D-3a) ──────────────────────────────────────


@pytest.mark.rule("D-3a", "X-19")
def test_a_layer_verdict_is_not_a_consent_signal():
    assert not consent_gate(_rule(PERSON_ALLOW, ORGANIZATION))
    assert not consent_gate(_rule(PERSON_DENY, ORGANIZATION_ALLOW))
    assert not narrows_person(PERSON_ALLOW)
    assert narrows_person(PERSON)


@pytest.mark.rule("D-3a")
def test_a_person_filter_beside_a_verdict_still_gates():
    gate = consent_gate(_rule(PERSON, ORGANIZATION_ALLOW))
    assert gate.signals == ("row_filters",)


# ── the resolver: kept, not dropped ──────────────────────────────


def test_the_resolver_keeps_a_person_layer_verdict(tmp_path: Path):
    rule = _load(tmp_path, PERSON_ALLOW, ORGANIZATION)
    assert [(f.handler, f.binds) for f in rule.row_filters] == [
        ("allow_all", "person"),
        ("organization_match", "organization"),
    ]
    assert not consent_gate(rule)


@pytest.mark.rule("C-10b")
def test_the_resolver_keeps_a_person_layer_deny(tmp_path: Path):
    """Dropped before, so the dataset read as ungated and served."""
    rule = _load(tmp_path, PERSON_DENY, ORGANIZATION_ALLOW)
    assert [f.handler for f in rule.row_filters] == ["deny_all", "allow_all"]


@pytest.mark.parametrize(
    ("row_filters", "message"),
    [
        ("oops", "row_filters is str, not a list"),
        (["junk"], r"row_filters\[0\] is str, not a mapping"),
        ([{"args": {"column": "c"}}], r"row_filters\[0\] names no handler"),
        ([{"handler": "rec_registry", "args": "c"}], "args is str, not a mapping"),
        ([{"handler": "rec_registry"}], "binds a person and declares no args"),
    ],
)
@pytest.mark.rule("C-10b")
def test_the_resolver_refuses_a_malformed_filter(tmp_path: Path, row_filters, message):
    path = write_governance(tmp_path, {"sources": {"a": {"row_filters": row_filters}}})
    with pytest.raises(ValueError, match=message):
        GovernanceResolver.from_file(path)


def test_null_args_read_as_absent(tmp_path: Path):
    rule = _load(
        tmp_path, {"handler": "member_wide", "binds": "organization", "args": None}
    )
    assert [f.handler for f in rule.row_filters] == ["member_wide"]


# ── the published offer ──────────────────────────────────────────


@pytest.mark.rule("X-19")
def test_a_verdict_is_not_published_as_a_consent_filter():
    mapper = GovernanceMapper(
        participant_id="provider",
        base_url="http://172.17.0.1:30001",
        profile=OdrlProfile(prefix="ds", namespace="https://w3id.org/dataspaces/ns/"),
    )
    asset = mapper.to_asset_create("grid.spans", _rule(PERSON_ALLOW, ORGANIZATION))
    assert asset["properties"]["ds:rowFilters"] is None


# ── the compliance check (D-3b) ──────────────────────────────────


@pytest.mark.rule("D-3b")
def test_an_organization_bound_dataset_with_a_person_allow_all_is_coherent(
    tmp_path: Path,
):
    """An impersonal, organization-bound dataset with both layers stated."""
    path = write_governance(
        tmp_path,
        {"sources": {"a": exposed_dataset(row_filters=[PERSON_ALLOW, ORGANIZATION])}},
    )
    result = run(path)
    assert "consent-coherence" not in codes(result.errors)
    assert "consent-coherence" not in codes(result.warnings)


@pytest.mark.rule("D-3b")
def test_personal_data_with_only_verdicts_has_no_per_subject_filter(tmp_path: Path):
    """A verdict is not the person filter consent needs: the existing warning."""
    path = write_governance(
        tmp_path,
        {
            "sources": {
                "a": exposed_dataset(
                    row_filters=[PERSON_ALLOW, ORGANIZATION_ALLOW],
                    dataspace={"consent_required": True},
                )
            }
        },
    )
    result = run(path)
    assert "consent-coherence" in codes(result.warnings)


# ── serialization ────────────────────────────────────────────────


def test_a_verdict_keeps_its_binds_when_defaults_are_excluded():
    """A deployment's assembly dumps resolved rules with `exclude_defaults`; `person` is
    the default, and a verdict without `binds` does not load again."""
    rule = _rule(PERSON_ALLOW, ORGANIZATION_ALLOW, PERSON)
    dumped = rule.model_dump(mode="json", exclude_defaults=True)["row_filters"]
    assert dumped[0] == {"handler": "allow_all", "binds": "person"}
    assert dumped[1] == {"handler": "allow_all", "binds": "organization"}
    assert "binds" not in dumped[2], "a filter's default stays a default"
    assert _rule(*dumped).row_filters == rule.row_filters
