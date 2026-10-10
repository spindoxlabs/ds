"""`row_filters[].binds` — only a filter binding a person is per-subject (celine-utils REQ-0010).

A filter binding an organization narrows an organization's rows inside the provider
platform. No person is behind such a row, so it is not a consent signal, it carries no
data subject, it is not published as a consent filter, and it is never put on the wire
with the consenting subjects. Forgetting the flag reads as `person` — it over-gates,
and the compliance check says so.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ds.governance.consent import consent_gate
from ds.governance.models import GovernanceRuleV2, RowFilter, subject_column
from ds.governance.resolver import GovernanceResolver

from .test_compliance_checks import codes, exposed_dataset, run, write_governance

PERSON = {"handler": "rec_registry", "args": {"column": "device_id"}}
ORGANIZATION = {
    "handler": "organization_match",
    "binds": "organization",
    "args": {"column": "rec_id"},
}
MEMBER_WIDE = {"handler": "member_wide", "binds": "organization"}


def _rule(*filters: dict, **extra) -> GovernanceRuleV2:
    return GovernanceRuleV2.model_validate({"row_filters": list(filters), **extra})


@pytest.mark.rule("D-3a")
def test_an_organization_filter_is_not_a_consent_signal():
    assert not consent_gate(_rule(ORGANIZATION))
    assert not consent_gate(_rule(MEMBER_WIDE))


@pytest.mark.rule("D-3a")
def test_an_undeclared_filter_still_gates():
    """The default is `person`: a forgotten flag over-gates, never under-gates."""
    assert consent_gate(_rule(PERSON)).signals == ("row_filters",)
    assert consent_gate(_rule({**PERSON, "binds": "person"})).signals == (
        "row_filters",
    )


@pytest.mark.rule("D-3a")
def test_one_person_filter_beside_an_organization_filter_gates():
    assert consent_gate(_rule(ORGANIZATION, PERSON)).signals == ("row_filters",)


def test_the_data_subject_column_comes_from_a_person_filter_only():
    assert subject_column(_rule(ORGANIZATION)) is None
    assert subject_column(_rule(ORGANIZATION, PERSON)) == "device_id"


def test_an_organization_filter_may_take_no_args():
    f = RowFilter.model_validate(MEMBER_WIDE)
    assert not f.binds_person
    assert f.args.column is None


def test_a_person_filter_without_a_column_does_not_load():
    with pytest.raises(ValidationError):
        RowFilter.model_validate({"handler": "rec_registry", "args": {}})


def test_an_unknown_binds_does_not_load():
    with pytest.raises(ValidationError):
        _rule({**ORGANIZATION, "binds": "community"})


def test_the_resolver_keeps_an_argless_organization_filter(tmp_path: Path):
    path = tmp_path / "governance.yaml"
    path.write_text(
        "sources:\n"
        "  a:\n"
        "    row_filters:\n"
        "      - handler: member_wide\n"
        "        binds: organization\n"
        "      - handler: argless_person\n"
    )
    rule = GovernanceResolver.from_file(path).resolve("a")
    # The organization filter survives without args; a person filter without them
    # is dropped exactly as before `binds` existed.
    assert [(f.handler, f.binds) for f in rule.row_filters] == [
        ("member_wide", "organization")
    ]


class TestCompliance:
    @pytest.mark.rule("C-10")
    def test_an_aggregate_with_only_organization_filters_is_clean(self, tmp_path: Path):
        """Contract-only, no person behind a row: no consent, no coherence error."""
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(row_filters=[ORGANIZATION])}}
        )
        assert "consent-coherence" not in codes(run(path).errors)
        assert "consent-coherence" not in codes(run(path).warnings)

    @pytest.mark.rule("C-10")
    def test_a_forgotten_flag_on_an_organization_filter_errors(self, tmp_path: Path):
        """Read as `person` on impersonal data: the existing contradiction error."""
        forgot = {k: v for k, v in ORGANIZATION.items() if k != "binds"}
        path = write_governance(
            tmp_path, {"sources": {"a": exposed_dataset(row_filters=[forgot])}}
        )
        assert "consent-coherence" in codes(run(path).errors)

    @pytest.mark.rule("C-10")
    @pytest.mark.parametrize(
        "declaration",
        [
            {"dataspace": {"consent_required": True}},
            {"classification": "pii"},
        ],
        ids=["consent_required", "pii"],
    )
    def test_personal_data_narrowed_only_by_organization_errors(
        self, tmp_path: Path, declaration
    ):
        """The likeliest cause: a person filter marked `binds: organization`."""
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(row_filters=[ORGANIZATION], **declaration)
                }
            },
        )
        assert "consent-coherence" in codes(run(path).errors)

    @pytest.mark.rule("C-10")
    def test_personal_data_with_a_person_and_an_organization_filter_is_clean(
        self, tmp_path: Path
    ):
        path = write_governance(
            tmp_path,
            {
                "sources": {
                    "a": exposed_dataset(
                        row_filters=[PERSON, ORGANIZATION],
                        classification="pii",
                        dataspace={"consent_required": True},
                    )
                }
            },
        )
        assert "consent-coherence" not in codes(run(path).errors)
